# AGENTS.md — Nepali Admin Copilot

## Project Goal
Extract Devanagari Unicode text from Nepali government PDFs (Preeti/Kantipur legacy fonts) via flatten-to-image + PaddleOCR, then translate to plain English with Gemini.

## Current Status: MVP v1
- `pdf_to_text.py` — full pipeline: PDF → images → PaddleOCR → filtered Unicode → optional Gemini translation → positioned HTML overlay
- `run.sh` — orchestrator script for common workflows
- `output/` — gitignored directory for all generated files
- Uses PP-OCRv5 with `devanagari_PP-OCRv5_mobile_rec` recognition model
- Output sorted by Y position (top-to-bottom reading order)
- Optional `--translate` flag pipes text through Gemini 2.5 Flash Lite for English translation
- Optional `--html` flag renders positioned HTML overlay with hover zoom + word-wrap

## Running
```bash
# Direct
ocr-env/bin/python pdf_to_text.py notice.pdf                         # Devanagari Unicode
ocr-env/bin/python pdf_to_text.py notice.pdf --html                   # HTML overlay (output/notice.html)
ocr-env/bin/python pdf_to_text.py notice.pdf --html --translate       # HTML + translation
export GEMINI_API_KEY='your-key'
ocr-env/bin/python pdf_to_text.py notice.pdf --translate             # English translation

# Orchestrator
./run.sh notice.pdf               # plain OCR to stdout
./run.sh notice.pdf --save        # save plain text to output/
./run.sh notice.pdf --html        # HTML overlay
./run.sh notice.pdf --translate   # translate
./run.sh notice.pdf --all         # HTML + translate, opens browser
```

## Setup
```bash
uv venv ocr-env --python 3.10
uv pip install --python ocr-env/bin/python -r requirements.txt setuptools
```

## Conventions
- **Entry point:** `pdf_to_text.py`
- **Orchestrator:** `run.sh` (executable, thin wrapper)
- **Dependencies:** `requirements.txt` (version ranges, not exact pins)
- **Venv:** `ocr-env/` (gitignored)
- **Intermediates:** `output/` (gitignored — png, html, ocr.txt, translated.txt)
- **Attempt folders** (`Attempt {1,2,3}/`) are prior explorations — ignore
- **`llm/idea.md`** has the full architecture blueprint

## OCR Model
- **Recognition:** `devanagari_PP-OCRv5_mobile_rec` (far better than v3 Devanagari model)
- **Detection:** `PP-OCRv5_mobile_det`
- Doc preprocessor disabled (clean digital PDFs don't need orientation classify or unwarping)
- Textline orientation disabled
- Models cache at `~/.paddlex/official_models/`

## Known Versions
- paddleocr 3.5.0 + paddlepaddle 3.2.2 is the known-good combo
- paddlepaddle 3.3.x has a bug (PIR format incompatibility)
- paddlepaddle 3.0.0 works but can only use PP-OCRv3 models

## Translation
- **Model:** `gemini-2.5-flash-lite` (cheapest available lite tier)
- API key via `GEMINI_API_KEY` env var or `--translate=KEY`
- System prompt includes a terminology glossary for government terms
- Free tier: 1,500 requests/day, 15 requests/minute

## HTML Overlay
- `--html` flag generates `output/<pdf>.html` + `output/<pdf>.png`
- Percentage-based positioning scales with browser
- Hover: text zooms large with word-wrap (no horizontal scroll)
- When `--translate` is combined, English appears in yellow below Devanagari
- Sidecar files: `<pdf>-ocr.txt` and `<pdf>-translated.txt`

## Known Issues
- Some conjuncts and rephas (half-letters) still misrecognized
- Very occasional Devanagari numeral confusion
- Low-confidence garbage detections filtered by <40% Devanagari ratio + length >= 2
- First run downloads ~80 MB of models
