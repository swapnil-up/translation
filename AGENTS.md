# AGENTS.md — Nepali Admin Copilot

## Project Goal
Extract Devanagari text from Nepali government PDFs. Two pipelines:
- **OCR** — legacy fonts (Preeti/Kantipur): flatten-to-image + PaddleOCR + optional Gemini translation
- **Vector** — CID-keyed fonts (Kalimati): pdfplumber + font mapping → structured tables (SQLite/CSV/Excel) with cross-verification

## Current Status: v2 (Budget extraction working)

### Vector Pipeline (`pdf_to_excel_v2.py`)
- Uses pdfplumber table detection with CID→Unicode font mapper (120 glyphs from 17 CMaps)
- **Text fallback**: when pdfplumber finds <10 rows but page has >500 chars, falls back to text-line reconstruction (`reconstruct_table_from_text`). Splits decoded text by lines, filters for 5+ digit codes or "जम्मा" keywords, routes through `parse_long_code_row` token-based extraction.
- 20-page test: 8 pages use table detection, 10 pages use text fallback
- Known structural diff on page 8: commissions (Rs 226.7M) not grouped under अर्थ मन्त्रालय, but page total is correct
- Pages 14-18: budget codes at 3 hierarchy levels (3/5/8-digit) — all present in PDF, not deduplicated

### Verification (`verify_budget.py`)
- Queries: `pages`, `page N --sum`, `section <name>`, `totals`, `verify`
- Cross-verification: per (page, section) sum of data rows vs stated totals

## Running

### OCR
```bash
ocr-env/bin/python pdf_to_text.py notice.pdf                  # Devanagari
ocr-env/bin/python pdf_to_text.py notice.pdf --html            # HTML overlay
export GEMINI_API_KEY='key'
ocr-env/bin/python pdf_to_text.py notice.pdf --translate       # Gemini translation
./run.sh notice.pdf --all                                      # orchestrator
```

### Vector (budget)
```bash
# First N pages → SQLite
ocr-env/bin/python pdf_to_excel_v2.py output/redbook.pdf --max-pages 20 --sqlite

# Slice a range
make slice PDF=output/redbook.pdf FROM=30 TO=50 DB=output/slice-30-50.db

# Verify
python3 verify_budget.py output/redbook-20.db verify
python3 verify_budget.py output/redbook-20.db page 10 --sum
```

## Setup
```bash
uv venv ocr-env --python 3.10
uv pip install --python ocr-env/bin/python -r requirements.txt setuptools
```

## Conventions
- **Venv:** `ocr-env/` (gitignored)
- **Output:** `output/` (gitignored — png, html, txt, db, xlsx, csv)
- **Dictionary data:** `dictionary/` (tracked); binaries in `dictionary-data/` (gitignored)
- **`llm/idea.md`** — full architecture blueprint

## Font Mapping
- Kalimati: 8 subsets sharing one CIDFont (696 glyphs, Identity-H encoding, no cmap)
- 17 ToUnicode CMap tables parsed → 120 CID→Unicode mappings + 21 fallback CIDs
- Preeti: Roman→Devanagari transliteration table (used for positioning spaces only)
- 70-entry word fix table for broken legacy glyph sequences (पर्देश→प्रदेश etc.)
- Scale multiplier: page header (हजार/लाख/करोड) ×1000/×100000/×10M

## Known Issues
- Some conjuncts/rephas still misrecognized (both pipelines)
- Nested subtotals on detail pages — each program total verified individually
- "स्रोत जम्मा नेपाल" sub-header lines flagged as total rows (no numeric impact)
- Truncated text at PDF crop boundary
- First OCR run downloads ~80 MB of models
