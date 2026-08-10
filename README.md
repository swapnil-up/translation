<div align="center">

# Nepali Admin Copilot

Extract Devanagari text from Nepali government PDFs — OCR for legacy fonts, structured extraction for CID-keyed budget documents.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Vue.js](https://img.shields.io/badge/Vue_3-4FC08D?style=for-the-badge&logo=vue.js&logoColor=white)](https://vuejs.org)
[![PaddleOCR](https://img.shields.io/badge/PaddleOCR-FF6F00?style=for-the-badge&logo=paddlepaddle&logoColor=white)](https://github.com/PaddlePaddle/PaddleOCR)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

</div>

## Overview

Nepali government documents use two kinds of PDFs:

- **Legacy font PDFs** (Preeti/Kantipur) — no embedded Unicode, text exists only as glyphs. Solution: OCR pipeline that rasterizes pages and runs PaddleOCR (Devanagari model).
- **CID-keyed budget PDFs** (Kalimati font) — embedded ToUnicode CMap tables but encoded with custom CID mappings. Solution: vector extraction via pdfplumber/PyMuPDF with CID→Unicode decoding.

Both pipelines are exposed as a **FastAPI web app** with a **Vue 3 SPA** frontend and also work as **CLI tools**.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Vue 3 SPA Frontend                    │
│  UploadView → ResultView (overlay / text / translation) │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP /api/*
┌──────────────────────────▼──────────────────────────────┐
│                    FastAPI Backend                        │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ OCR API  │  │ Translation  │  │ Budget Extract   │   │
│  │ Endpoints│  │ Service      │  │ Endpoints        │   │
│  └────┬─────┘  └──────┬───────┘  └───────┬──────────┘   │
│       │               │                  │               │
│  ┌────▼─────┐   ┌─────▼───────┐   ┌──────▼──────────┐   │
│  │ PaddleOCR│   │ Google      │   │ pdfplumber /    │   │
│  │ (OCR)    │   │ Gemini      │   │ PyMuPDF (CID)   │   │
│  └──────────┘   └─────────────┘   └─────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

## Features

### OCR Pipeline (Legacy Fonts)
- Upload Nepali government PDFs (Preeti/Kantipur fonts)
- PDF rasterized at configurable DPI → PaddleOCR Devanagari recognition
- Output: Unicode text with word-level bounding box positions
- Optional Gemini translation to English with context-aware batch translation
- HTML overlay with positioned text blocks over page images
- Async task processing with progress polling

### Vector Budget Extraction (CID Fonts)
- Two extraction engines: pdfplumber (v2) and PyMuPDF (v3)
- Parses 17+ ToUnicode CMap tables from embedded fonts
- Extracts structured budget rows (budget code, description, actual/revised/estimate columns)
- Auto-detects scale multipliers (हजार=×1,000, लाख=×100,000, करोड=×10,000,000)
- Exports to SQLite, CSV, Excel with cross-verification against stated totals

### Web App
- Drag-and-drop PDF upload (up to 50MB)
- Real-time progress polling with queue position
- Interactive overlay view with hover zoom and translation display
- Side-by-side Devanagari/English text view
- Download as TXT or CSV

### CLI Tools
- `pdf_to_text.py` — single-file OCR with optional translation and HTML overlay
- `run.sh` — orchestrator wrapper
- `pdf_to_excel_v2.py` / `pdf_to_excel_v3.py` — budget extraction
- `verify_budget.py` — cross-verify extracted totals

### Notice Automation Pipeline
- `scripts/scrape_notices.py` — scrapes parliament notices list (1,300+ entries) and backfills PDF URLs
- `scripts/process_notice.py` — picks 1 pending notice, downloads PDF, runs OCR + translation, saves both
- `notices.json` — manifest tracking status (pending/done/failed) for all notices
- GitHub Actions: weekly scrape + daily backfill translation (`GEMINI_API_KEY` secret required)

```bash
# Scrape notice list (fast, incremental)
.venv/bin/python scripts/scrape_notices.py

# Backfill PDF URLs
.venv/bin/python scripts/scrape_notices.py --backfill

# Process one notice (download, OCR, translate)
GEMINI_API_KEY=$key .venv/bin/python scripts/process_notice.py

# Output: output/{title}.txt (translation) + output/{title}-ocr.txt (Devanagari)
```

## Tech Stack

| Component | Technology |
|---|---|
| Backend | FastAPI + uvicorn |
| OCR | PaddleOCR PP-OCRv5 (Devanagari model) |
| Translation | Google Gemini 2.5 Flash Lite |
| PDF Vector | pdfplumber, PyMuPDF |
| Frontend | Vue 3 + TypeScript + Vite + Tailwind CSS |
| Container | Docker (multi-stage) |
| Deployment | Hugging Face Spaces |
| Data | SQLite, openpyxl (Excel) |

## Quick Start

```bash
# Local development
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev

# CLI OCR
python pdf_to_text.py notice.pdf --html --translate
```

## Project Structure

```
├── backend/                  # FastAPI app
│   ├── app/
│   │   ├── main.py          # App entry, routes, CORS
│   │   ├── config.py        # Pydantic settings
│   │   ├── schemas.py       # Pydantic models
│   │   ├── api/ocr.py       # OCR API endpoints
│   │   └── services/
│   │       ├── ocr_service.py    # Async OCR pipeline
│   │       └── translation.py    # Gemini translation
│   └── requirements.txt
├── frontend/                 # Vue 3 SPA
│   └── src/
│       ├── views/           # UploadView, ResultView
│       ├── components/      # FileUpload, OcrProgress, OcrResult, OcrOverlay
│       ├── services/api.ts  # API client
│       └── router/          # Vue Router
├── budget/                  # Budget extraction tools
│   ├── pdf_to_excel_v2.py  # pdfplumber engine
│   ├── pdf_to_excel_v3.py  # PyMuPDF engine
│   └── verify_budget.py    # Cross-verification
├── dictionary/              # Nepali-English dict builder
├── scripts/                 # Notice automation
│   ├── scrape_notices.py   # Scraper (list + PDF backfill)
│   └── process_notice.py   # Download, OCR, translate pipeline
├── .github/workflows/      # GitHub Actions
│   ├── scrape-notices.yml  # Weekly scrape
│   └── translate-notices.yml # Daily backfill translation
├── notices.json            # Notice manifest (current 7th HoR, ~124 entries)
├── notices-6th-hor.json    # Archive of old 6th-HoR notices (1,185 entries, keeps translation links)
├── Dockerfile               # Production build
└── requirements.txt         # Root dependencies
```

## Deployment

One-click deploy to Hugging Face Spaces:

```bash
git remote add space https://huggingface.co/spaces/<user>/<space>
git push space main
```

Set `GEMINI_API_KEY` in Space secrets for translation support.

## GitHub Actions Setup

1. Add `GEMINI_API_KEY` to repo secrets (Settings → Secrets and variables → Actions)
2. The scrape workflow runs Monday 6am, translate workflow runs daily 4am
3. Both can also be triggered manually from the Actions tab

## License

MIT