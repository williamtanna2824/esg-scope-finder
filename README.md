# ESG Scope Finder

A FastAPI web app that finds corporate ESG/sustainability reports and extracts **Scope 1, Scope 2, and Scope 3** greenhouse gas emissions using GPT-4o.

Built for FIN 294 — search a company and year, get structured emissions data with page citations, charts, and Q&A over the report.

## Features

- **PDF discovery** — searches the web (via Serper) for the best-matching sustainability report for a company and year
- **Scope extraction** — pulls Scope 1–3 values, units, basis, page numbers, and confidence scores from the PDF
- **Company profile** — shows website, logo, and description for the searched company
- **Interactive UI** — bar chart comparison, voice input, JSON export, and NotebookLM text export
- **Report Q&A** — ask natural-language questions about the extracted report text

## Tech Stack

- **Backend:** FastAPI, OpenAI GPT-4o, pdfplumber, httpx
- **Frontend:** HTML/CSS/JS with Chart.js
- **Search:** [Serper](https://serper.dev) Google Search API

## Project Structure

```
esg_scope1_app/
├── backend.py          # FastAPI server and API routes
├── requirements.txt    # Python dependencies
├── s.env.example       # API key template (copy to s.env locally)
├── static/
│   └── searchai.html   # Frontend UI
└── README.md
```

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/williamtanna2824/esg-scope-finder.git
cd esg-scope-finder
```

### 2. Install dependencies

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure API keys

You need a [Serper API key](https://serper.dev) and an [OpenAI API key](https://platform.openai.com).

**Local development** — copy the example file and fill in your keys:

```bash
cp s.env.example s.env
```

**Hosted deployment** (Render, Railway, etc.) — set these as environment variables:

| Variable         | Description              |
|------------------|--------------------------|
| `SERPER_API_KEY` | Serper search API key    |
| `OPENAI_API_KEY` | OpenAI API key (GPT-4o)  |

> Never commit `s.env` or real API keys to GitHub.

### 4. Run the app

```bash
uvicorn backend:app --host 0.0.0.0 --port 8000 --reload
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

## API Endpoints

| Method | Path             | Description                          |
|--------|------------------|--------------------------------------|
| `GET`  | `/`              | Frontend UI                          |
| `GET`  | `/health`        | Health check                         |
| `POST` | `/find_esg_pdf`  | Find the best ESG PDF for a company  |
| `POST` | `/extract_scopes`| Extract Scope 1–3 from a PDF URL     |
| `POST` | `/ask_about_pdf` | Q&A over a PDF                       |
| `POST` | `/scope_text`    | Raw scope-related text from a PDF    |

### Example: Find a report

```bash
curl -X POST http://localhost:8000/find_esg_pdf \
  -H "Content-Type: application/json" \
  -d '{"company": "JPMorgan Chase", "year": 2024}'
```

### Example: Extract scopes

```bash
curl -X POST http://localhost:8000/extract_scopes \
  -H "Content-Type: application/json" \
  -d '{"pdf_url": "https://example.com/report.pdf", "company": "JPMorgan Chase", "year": 2024}'
```

## How It Works

1. User enters a company name and report year.
2. Serper searches for sustainability/ESG PDFs and scores candidates by company match, year, and ESG keywords.
3. The best PDF is downloaded and parsed with pdfplumber, focusing on pages mentioning Scope 1–3.
4. GPT-4o extracts structured emissions data (values, units, page numbers, confidence) as JSON.
5. Results are displayed in the UI with charts and optional Q&A.

## License

Academic project — FIN 294.
