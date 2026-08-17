# Bill Tracker

Nepali parliamentary notice and verbatim tracking pipeline. Scrapes, OCRs, translates, and indexes parliamentary documents into pgvector for semantic search.

## Components

| Directory | Purpose |
|-----------|---------|
| `scripts/` | Python CLI scripts for scraping, processing, and upserting |
| `backend/` | FastAPI web app with OCR API endpoints |
| `frontend/` | Vue 3 SPA for PDF upload and result viewing |
| `pdf_to_text.py` | OCR CLI (used by process scripts) |
| `notices.json` | Notice manifest (7th HoR, ~124 entries) |
| `verbatims.json` | Verbatim manifest (NA sessions 19+) |
| `.env` | API keys (`GEMINI_API_KEY`, `DATABASE_URL`) |
| `.venv/` | Python virtual environment (gitignored) |

## Scripts

| Script | Description |
|--------|-------------|
| `scripts/scrape_notices.py` | Scrapes `hr.parliament.gov.np` notices into `notices.json` |
| `scripts/process_notice.py` | OCR + Gemini translation for one pending notice |
| `scripts/upsert_notice.py` | Embed + upsert structured JSON to pgvector |
| `scripts/scrape_verbatims.py` | Scrapes NA verbatims from API into `verbatims.json` |
| `scripts/process_verbatim.py` | Segmented OCR + Gemini translation for verbatims |
| `scripts/upsert_verbatim.py` | Embed + upsert verbatim JSON to pgvector |
| `scripts/init_db.py` | Creates pgvector schema (notices, chunks, verbatims, verbatim_chunks) |

## Running

All scripts run from the **repo root**:

```bash
# Scrape notices
python bill-tracker/scripts/scrape_notices.py [--backfill] [--list-only]

# Process one notice (OCR + translate)
GEMINI_API_KEY=$key python bill-tracker/scripts/process_notice.py --max-count 1

# Upsert to pgvector
python bill-tracker/scripts/upsert_notice.py translations/*.json

# Same pattern for verbatims
python bill-tracker/scripts/scrape_verbatims.py
GEMINI_API_KEY=$key python bill-tracker/scripts/process_verbatim.py --max-count 1
python bill-tracker/scripts/upsert_verbatim.py translations/Verbatim_*.json
```

## Backend

```bash
cd bill-tracker/backend
uvicorn app.main:app --reload --port 8000
```

## Output Files

| File | Location | Content |
|------|----------|---------|
| `{stem}-ocr.txt` | `translations/` | Raw Devanagari OCR text |
| `{stem}.txt` | `translations/` | Full English translation |
| `{stem}.json` | `translations/` | Structured JSON (sections, speakers, bills, tags) |

## Setup

```bash
cd bill-tracker
python -m venv .venv && source .venv/bin/activate
pip install -r ../requirements.txt
cp .env.example .env  # fill in GEMINI_API_KEY, DATABASE_URL
```

## Dependencies

Uses the root `requirements.txt` for: `paddleocr`, `pdf2image`, `requests`, `beautifulsoup4`, `lxml`, `psycopg`.
Backend has its own `requirements.txt` with `fastapi`, `uvicorn`, `google-genai`.
