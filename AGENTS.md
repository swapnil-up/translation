# AGENTS.md — Nepali Admin Copilot

## Project Goal
Extract Devanagari text from Nepali government PDFs. Three pipelines:
- **OCR** — legacy fonts (Preeti/Kantipur): flatten-to-image + PaddleOCR + optional Gemini translation
- **Vector (v2)** — CID-keyed fonts (Kalimati): pdfplumber + font mapping → structured tables
- **Vector (v3)** — CID-keyed fonts via PyMuPDF + post-processing tables (redbook8283.pdf, 556pp)

## Current Status: v3 (PyMuPDF extraction working)

### v3 Pipeline (`pdf_to_excel_v3.py`)
Uses PyMuPDF's built-in ToUnicode CMap decoding, supplemented with:
- **CID→Unicode table** (CID_CHAR_MAP): ~40 integer CID→Devanagari mappings for CIDs not in any font's ToUnicode CMap
- **Exact word-fix table** (EXACT_FIXES): ~100 entries for garbled word patterns, applied both pre- and post-CID mapping
- **State-machine line parser**: handles multi-line budget rows (code+desc on one line, 6 amounts on subsequent lines)
- **Scale inheritance**: detects लाख/करोड per page; continuation pages inherit scale from first detail page
- **Priority code handling**: extracts P1/0/3 priority/sdg/gender codes from multi-line patterns

**Results** (pages 17-60 of redbook8283.pdf):
- 1,319 data rows from 41 pages with budget codes
- 111 total rows (is_total=1)
- Pages 3-4: 39-62 rows (summary index)
- Pages 17-34: 31-36 rows each (detail budgets)
- Pages 35+: 11-12 rows each (summary by ministry)
- Scale: all detail pages in लाख (×100,000)
- Descriptions clean; remaining garbled chars use word-fix table

### Data Columns
| # | DB Column | Description |
|---|-----------|-------------|
| 1 | `year_actual` | यथार्थ (actual) |
| 2 | `year_revised` | संशोधित (revised) |
| 3 | `year_estimate` | अनुमान (estimate) |
| 4 | `total` | जम्मा (total) |
| 5 | `current_exp` | चालु (current expenditure) |
| 6 | `capital_exp` | पूँजीगत (capital expenditure) |
| 7 | `financial` | वित्तीय व्यवस्था |
| 8 | `baideshik_anudan` | बैदेशिक अनुदान |
| 9 | `baideshik_rin` | बैदेशिक ऋण |
| 10 | `prathamikta_sanket` | प्राथमिकता सङ्केत |
| 11 | `raniti_sanket` | रणनीति सङ्केत |
| 12 | `laigik_sanket` | लैङ्गिक सङ्केत |

- Columns 7-9 not yet populated on detail pages (only 6 amounts extracted)
- Priority codes captured for rows with P-prefix pattern
- Summary pages (35+) have different column layout; amounts may need different mapping

### v2 Pipeline (`pdf_to_excel_v2.py`) — unchanged, for redbook.pdf only

## Running

### OCR
```bash
ocr-env/bin/python pdf_to_text.py notice.pdf                          # Devanagari
ocr-env/bin/python pdf_to_text.py notice.pdf --html                   # HTML overlay
export GEMINI_API_KEY='key' && ocr-env/bin/python pdf_to_text.py notice.pdf --translate
```

### v3 (redbook8283.pdf)
```bash
# Pages 1-60 → SQLite
python3 pdf_to_excel_v3.py output/redbook8283.pdf --max-pages 60 --sqlite -o output/redbook-v3-60.db

# Full extraction
python3 pdf_to_excel_v3.py output/redbook8283.pdf --sqlite -o output/redbook-v3.db
```

### v2 (redbook.pdf)
```bash
ocr-env/bin/python pdf_to_excel_v2.py output/redbook.pdf --max-pages 20 --sqlite
make slice PDF=output/redbook.pdf FROM=30 TO=50 DB=output/slice-30-50.db
```

## Setup
```bash
uv venv ocr-env --python 3.10
uv pip install --python ocr-env/bin/python -r requirements.txt setuptools
```

## Conventions
- **Venv:** `ocr-env/` (gitignored)
- **Output:** `output/` (gitignored — png, html, txt, db, xlsx, csv)
- **Translations:** `translations/` (tracked — committed OCR text + English translations)
- **Dictionary data:** `dictionary/` (tracked); binaries in `dictionary-data/` (gitignored)
- **`llm/idea.md`** — full architecture blueprint

## Font Architecture (redbook8283.pdf)
- Type0 font with Identity-H encoding, per-page font subsets each with own ToUnicode CMap
- Fitz applies the CMap correctly for ∼95% of glyphs; unmapped CIDs fall through to Identity-H → chr(cid)
- Control chars (\x04, \t, \x0e, etc.) for unmapped CIDs; literal ASCII chars (> < @ ^ 3 B) for higher-range unmapped CIDs
- Same CID maps to different Devanagari across different font instances → word-level fixes required
- Scale multiplier: page header (हजार/लाख/करोड) ×1000/×100000/×10M

## Known Issues
- Columns 7-9 (financial, baideshik_anudan, baideshik_rin) not captured on detail pages
- Summary pages (35+) may have different column ordering — not yet verified
- Per-instance CID mapping differences → word-fix table grows per page range
- Pages 1-16 (TOC) produce noise rows with empty descriptions
- No cross-verification yet (verify_budget.py not adapted for v3 schema)

## Notice Automation Pipeline

### Scripts
- `scripts/scrape_notices.py` — scrapes `hr.parliament.gov.np` notices table (44 pages, 1,302 entries). Two modes: `--list-only` (fast, incremental) and `--backfill` (fetches detail pages for PDF URLs). Output: `notices.json`.
- `scripts/process_notice.py` — picks 1 pending notice from manifest, backfills PDF URL if missing, downloads PDF, runs PaddleOCR (OCR only), then calls Gemini with a structured JSON prompt. Saves three files: `{stem}-ocr.txt` (Devanagari), `{stem}.txt` (full English translation), `{stem}.json` (structured metadata with sections, speakers, bills, agenda tags).
- `scripts/upsert_notice.py` — reads a structured `{stem}.json` file, chunks sections, generates embeddings via `text-embedding-004`, and upserts to pgvector (both notice record + chunks).
- `scripts/init_db.py` — creates the pgvector schema (`notices` + `chunks` tables).

### Output files (per notice)
| File | Content |
|------|---------|
| `translations/{stem}-ocr.txt` | Raw Devanagari OCR text |
| `translations/{stem}.txt` | Full English translation (narrative) |
| `translations/{stem}.json` | Structured JSON with session, sections, speakers, bills, tags |

### Database model (pgvector)
```sql
notices (id, title UNIQUE, date_bs, date_ad, meeting_type, meeting_number,
         chairperson, agenda_tags, ministries_mentioned, full_translation_en, ...)

chunks (id, notice_id FK, chunk_index, section_name, chunk_text,
        embedding VECTOR(768), speaker_names TEXT[], key_issues TEXT[], ...)
```
- Upsert key: `notices.title` (unique). Rerunning the same notice updates in place.
- Chunks are deleted + re-inserted on each upsert (simplifies iteration).

### Running locally (requires Postgres + pgvector, or Supabase/Neon URL)

**With Docker:**
```bash
docker compose up -d                              # start pgvector container
.venv/bin/python scripts/init_db.py               # create schema
GEMINI_API_KEY=$key .venv/bin/python scripts/process_notice.py --max-count 1
.venv/bin/python scripts/upsert_notice.py translations/Notice_*.json
```

**With Supabase/Neon (no Docker):**
```bash
.venv/bin/python scripts/init_db.py --url "postgresql://..."
GEMINI_API_KEY=$key .venv/bin/python scripts/process_notice.py --max-count 1
.venv/bin/python scripts/upsert_notice.py translations/Notice_*.json --url "postgresql://..."
```

### Running with Supabase/Neon
```bash
# Create free project at supabase.com or neon.tech, get connection string
.venv/bin/python scripts/init_db.py --url "postgresql://user:pass@host:5432/db"
.venv/bin/python scripts/upsert_notice.py translations/*.json
```

### Gemini structured prompt
Uses `response_mime_type="application/json"` with a schema that returns both `full_translation_en` + structured fields in one call. Model: `gemini-2.5-flash-lite` with `temperature=0.2`.

### Manifest (`notices.json`)
| Field | Description |
|-------|-------------|
| `serial` | Row number from table |
| `title` | Notice title (e.g. "Notice 2083-03-31") |
| `url` | Detail page URL |
| `pdf_url` | Direct PDF attachment URL |
| `status` | `pending` / `done` / `failed` / `no_pdf` |
| `scraped_at` | Date first discovered |
| `ocr_path` | Path to saved OCR text (when done) |
| `translated_path` | Path to saved translation (when done) |
| `structured_path` | Path to structured JSON (when done, new notices only) |

### GitHub Actions
- `scrape-notices.yml` — weekly Monday 6am, commits new notices to `notices.json`
- `translate-notices.yml` — daily 4am, processes 1 pending notice, commits translated output

### SSL Note
The parliament site has a misconfigured SSL cert — both scripts use `verify=False`. The GitHub Actions runners also hit this issue; the `urllib3.disable_warnings()` in the scripts suppresses the noise.
