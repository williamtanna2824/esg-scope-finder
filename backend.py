import os
import io
import json
from typing import Optional, Dict, Any

import httpx
import pdfplumber
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI

# =========================================================
# ENV + CLIENTS
# =========================================================

load_dotenv("s.env")

SERPER_KEY = os.getenv("SERPER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not SERPER_KEY:
    raise RuntimeError("SERPER_API_KEY is missing. Set it in s.env or as an environment variable.")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is missing. Set it in s.env or as an environment variable.")

client = OpenAI(api_key=OPENAI_API_KEY)

# =========================================================
# FASTAPI APP
# =========================================================

app = FastAPI(title="ESG Scope Finder")

# IMPORTANT: pass the class, not an instance
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# Utility
# =========================================================

def http_error_to_http_exception(prefix: str, err: Exception) -> HTTPException:
    if isinstance(err, httpx.HTTPStatusError):
        status = err.response.status_code
        text = err.response.text[:300]
        detail = f"{prefix} HTTP {status}: {text}"
        print(f"[{prefix}] {detail}")
        return HTTPException(status_code=502, detail=detail)
    detail = f"{prefix} request failed: {err}"
    print(f"[{prefix}] {detail}")
    return HTTPException(status_code=502, detail=detail)

# =========================================================
# SERPER SEARCH (PDF Finder)
# =========================================================

def serper_search(query: str) -> Dict[str, Any]:
    headers = {
        "X-API-KEY": SERPER_KEY,
        "Content-Type": "application/json",
    }
    payload = {"q": query}

    try:
        with httpx.Client(timeout=15) as http:
            r = http.post("https://google.serper.dev/search", headers=headers, json=payload)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise http_error_to_http_exception("Serper", e)


def is_pdf(url: str) -> bool:
    if url.lower().endswith(".pdf"):
        return True
    try:
        with httpx.Client(timeout=8, follow_redirects=True) as http:
            r = http.head(url)
        return "pdf" in r.headers.get("Content-Type", "").lower()
    except Exception:
        return False


def find_pdf_candidates(company: str, year: int):
    query = f'"{company}" {year} sustainability report pdf'
    data = serper_search(query)
    pdfs = []
    for item in data.get("organic", []):
        url = item.get("link") or item.get("url")
        if url and is_pdf(url):
            pdfs.append(
                {
                    "title": item.get("title"),
                    "url": url,
                    "snippet": item.get("snippet", ""),
                }
            )
    return pdfs


def score_candidate(c, company, year):
    text = (c["title"] or "").lower() + " " + (c["snippet"] or "").lower()
    url = c["url"].lower()
    score = 0.0

    # Company match
    if company.lower().split()[0] in text or company.lower().split()[0] in url:
        score += 0.3

    # Year match
    if str(year) in text or str(year) in url:
        score += 0.3

    # ESG keywords
    if any(k in text for k in ["sustainability", "esg", "csr", "climate", "impact", "report"]):
        score += 0.4

    return score


def find_best_esg_pdf(company: str, year: int) -> Optional[dict]:
    candidates = find_pdf_candidates(company, year)
    if not candidates:
        return None

    # SORT BY SCORE ONLY → avoids dict comparison TypeError
    scored = sorted(
        [(score_candidate(c, company, year), c) for c in candidates],
        key=lambda x: x[0],
        reverse=True,
    )

    best_score, best = scored[0]
    confidence_pct = int(round(min(best_score, 1.0) * 100))

    return {
        "company": company,
        "year": year,
        "pdf_url": best["url"],
        "title": best["title"],
        "snippet": best["snippet"],
        "confidence": confidence_pct,
    }


def get_company_profile(name: str):
    try:
        data = serper_search(f"{name} company website")
        if not data.get("organic"):
            return {"name": name, "website": None, "logo_url": None, "description": None}

        top = data["organic"][0]
        url = top.get("link") or top.get("url")
        snippet = top.get("snippet", "")
        domain = url.split("://")[1].split("/")[0] if "://" in url else None
        logo = f"https://logo.clearbit.com/{domain}" if domain else None

        return {"name": name, "website": url, "logo_url": logo, "description": snippet}
    except Exception:
        return {"name": name, "website": None, "logo_url": None, "description": None}

# =========================================================
# PDF Extraction
# =========================================================

def download_pdf_bytes(url: str) -> bytes:
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as http:
            r = http.get(url)
            r.raise_for_status()
            return r.content
    except Exception as e:
        raise http_error_to_http_exception("PDF download", e)


def extract_scope_pages(pdf_bytes: bytes, max_pages: int = 12) -> str:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = []
            matches_found = False

            for idx, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                lower = text.lower()
                if any(k in lower for k in ["scope 1", "scope-1", "scope 2", "scope-2", "scope 3", "scope-3"]):
                    matches_found = True
                    for j in range(max(0, idx - 1), min(idx + 2, len(pdf.pages))):
                        t = pdf.pages[j].extract_text() or ""
                        pages.append(f"--- PAGE {j+1} ---\n{t}")
                        if len(pages) >= max_pages:
                            break

            if not matches_found:
                for i in range(min(max_pages, len(pdf.pages))):
                    text = pdf.pages[i].extract_text() or ""
                    pages.append(f"--- PAGE {i+1} ---\n{text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF parse error: {e}")

    combined = "\n\n".join(pages)
    if not combined.strip():
        raise HTTPException(status_code=500, detail="PDF text empty")
    return combined

# =========================================================
# GPT-4o Scope Extraction
# =========================================================

def llm_extract_scopes(text_block: str, company: Optional[str] = None, year: Optional[int] = None):
    context = ""
    if company:
        context += f"Company: {company}\n"
    if year:
        context += f"Year: {year}\n"

    prompt = f"""
{context}
You are extracting Scope 1, Scope 2, and Scope 3 greenhouse gas emissions from a corporate ESG/sustainability report. 

Pages are marked like:

--- PAGE 5 ---

You must return ONLY a single JSON object in this exact structure:

{{
  "scope1": {{"numeric_value": <number or null>, "units": "<string>", "year": "<string>", "basis": "<string>", "raw_snippet": "<string>", "page_number": <number or null>, "confidence": <0-100>}},
  "scope2": {{"numeric_value": <number or null>, "units": "<string>", "year": "<string>", "basis": "<string>", "raw_snippet": "<string>", "page_number": <number or null>, "confidence": <0-100>}},
  "scope3": {{"numeric_value": <number or null>, "units": "<string>", "year": "<string>", "basis": "<string>", "raw_snippet": "<string>", "page_number": <number or null>, "confidence": <0-100>}},
  "summary": "<2-4 sentence summary of emissions profile>",
  "overall_confidence": <0-100>
}}

Rules:
- numeric_value must be a number (no commas) or null if not found.
- page_number must be the page from the --- PAGE X --- markers or null if not sure.
- confidence is an integer from 0 to 100.
- If a scope is not found, set numeric_value = null, page_number = null, confidence = 0.

TEXT:
{text_block}
""".strip()

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise ESG data extractor. Only use information present in the text.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI extraction error: {e}")

# =========================================================
# GPT-4o Q&A
# =========================================================

def llm_pdf_qa(text_block: str, question: str) -> str:
    prompt = f"""
You are an ESG analyst. Answer the question using ONLY the report text below.
If the answer is not clearly supported, say you are not certain.

TEXT:
{text_block}

QUESTION: {question}
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.2,
            messages=[
                {"role": "system", "content": "Answer concisely and strictly from the provided text."},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI QA error: {e}")

# =========================================================
# Pydantic MODELS
# =========================================================

class ESGRequest(BaseModel):
    company: str
    year: int

class ScopeRequest(BaseModel):
    pdf_url: str
    company: Optional[str] = None
    year: Optional[int] = None

class QARequest(BaseModel):
    pdf_url: str
    question: str
    company: Optional[str] = None
    year: Optional[int] = None

# =========================================================
# API ENDPOINTS
# =========================================================

@app.post("/find_esg_pdf")
def api_find_esg_pdf(body: ESGRequest):
    pdf = find_best_esg_pdf(body.company, body.year)
    if not pdf:
        raise HTTPException(status_code=404, detail="No ESG PDF found")
    pdf["company_profile"] = get_company_profile(body.company)
    return pdf


@app.post("/extract_scopes")
def api_extract_scopes(body: ScopeRequest):
    pdf_bytes = download_pdf_bytes(body.pdf_url)
    text_block = extract_scope_pages(pdf_bytes)
    scopes = llm_extract_scopes(text_block, company=body.company, year=body.year)
    return {
        "pdf_url": body.pdf_url,
        "company": body.company,
        "year": body.year,
        "scopes": scopes,
    }


@app.post("/ask_about_pdf")
def api_ask(body: QARequest):
    pdf_bytes = download_pdf_bytes(body.pdf_url)
    text_block = extract_scope_pages(pdf_bytes)
    answer = llm_pdf_qa(text_block, body.question)
    return {"answer": answer}


@app.post("/scope_text")
def api_scope_text(body: ScopeRequest):
    pdf_bytes = download_pdf_bytes(body.pdf_url)
    text_block = extract_scope_pages(pdf_bytes)
    return {"text": text_block}

# =========================================================
# STATIC FRONTEND
# =========================================================

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(STATIC_DIR, "searchai.html"))

@app.get("/health")
def health():
    return {"status": "ok"}
