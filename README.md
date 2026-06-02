# ESG Scope Finder

FastAPI app that searches for corporate ESG/sustainability PDFs and extracts Scope 1, 2, and 3 greenhouse gas emissions.

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/williamtanna2824/esg-scope-finder.git
   cd esg-scope-finder
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Configure API keys (choose one):
   - **Local:** copy `s.env.example` to `s.env` and add your keys
   - **Hosted (Render, Railway, etc.):** set `SERPER_API_KEY` and `OPENAI_API_KEY` as environment variables

4. Run the server:
   ```bash
   uvicorn backend:app --host 0.0.0.0 --port 8000 --reload
   ```

5. Open [http://localhost:8000](http://localhost:8000) in your browser.

## API

- `GET /health` — health check
- `GET /` — frontend UI
- See `backend.py` for search and extraction endpoints.
