# Nepali Admin Copilot

Extract text from Nepali government PDFs. Two pipelines:

- **OCR** — for legacy font PDFs (Preeti/Kantipur): flatten to image → PaddleOCR → Devanagari Unicode
- **Vector** — for CID-keyed budget PDFs (Kalimati font): pdfplumber → font-mapped Devanagari → structured tables (SQLite/CSV/Excel)

---

## Pipeline 1: OCR (legacy fonts)

```bash
uv venv ocr-env --python 3.10
uv pip install --python ocr-env/bin/python -r requirements.txt setuptools

# Plain OCR to stdout
ocr-env/bin/python pdf_to_text.py notice.pdf

# HTML overlay with hover zoom
ocr-env/bin/python pdf_to_text.py notice.pdf --html

# Translate to English via Gemini 2.5 Flash Lite
export GEMINI_API_KEY='your-key'
ocr-env/bin/python pdf_to_text.py notice.pdf --translate
```

Or use the orchestrator:

```bash
./run.sh notice.pdf               # Plain OCR
./run.sh notice.pdf --save        # Save to output/notice-ocr.txt
./run.sh notice.pdf --html        # HTML overlay
./run.sh notice.pdf --translate   # Translate
./run.sh notice.pdf --all         # HTML + translate, opens browser
```

First run downloads PaddleOCR model weights (~80 MB).

---

## Pipeline 2: Vector budget extraction (CID fonts)

For budget PDFs with embedded CID-keyed fonts (Kalimati). Extracts structured tables via pdfplumber + CID→Unicode decoder, then exports to SQLite/CSV/Excel with cross-verification against stated totals.

### Quick start

```bash
# First 20 pages → SQLite
ocr-env/bin/python pdf_to_excel_v2.py output/redbook.pdf --max-pages 20 --sqlite

# Same but Excel
ocr-env/bin/python pdf_to_excel_v2.py output/redbook.pdf --max-pages 20

# Per-page CSV
ocr-env/bin/python pdf_to_excel_v2.py output/redbook.pdf --max-pages 20 --csv
```

### Slice any page range

```bash
# Pages 30-50 → slice-30-50.pdf → slice-30-50.db
make slice PDF=output/redbook.pdf FROM=30 TO=50 DB=output/slice-30-50.db
```

Or manually:

```bash
python3 -c "from pypdf import PdfWriter,PdfReader; w=PdfWriter(); r=PdfReader('output/redbook.pdf'); [w.add_page(r.pages[i]) for i in range(29,50)]; w.write('output/slice.pdf')" && ocr-env/bin/python pdf_to_excel_v2.py output/slice.pdf --sqlite
```

### Verify against stated totals

```bash
python3 verify_budget.py output/redbook-20.db pages          # page inventory
python3 verify_budget.py output/redbook-20.db page 8 --sum   # show rows + compare totals
python3 verify_budget.py output/redbook-20.db section अर्थ   # drill into a section
python3 verify_budget.py output/redbook-20.db totals         # all stated total rows
python3 verify_budget.py output/redbook-20.db verify         # full cross-check
```

### Manual cross-check with SQLite

After generating the DB, verify individual pages against the PDF:

```bash
# All rows on page 8, columnar
sqlite3 output/redbook-20.db -column -header "
SELECT id, budget_code, substr(description,1,40) AS desc,
       year_actual, year_revised, year_estimate, total,
       CASE WHEN is_total_row THEN 'TOTAL' WHEN is_grand_total_row THEN 'GRAND' ELSE '' END AS flag
FROM raw_budget_lines WHERE page_number = 8 ORDER BY id;
"

# Sum data rows, compare to stated total
sqlite3 output/redbook-20.db "
SELECT 'DATA SUM' AS kind, SUM(total) FROM raw_budget_lines
WHERE page_number = 8 AND is_total_row = 0 AND is_grand_total_row = 0
UNION ALL
SELECT 'STATED TOTAL', SUM(total) FROM raw_budget_lines
WHERE page_number = 8 AND (is_total_row = 1 OR is_grand_total_row = 1);
"

# All total rows across all pages
sqlite3 output/redbook-20.db -column -header "
SELECT page_number, inferred_section, total, substr(description,1,50) AS desc
FROM raw_budget_lines WHERE is_total_row = 1 OR is_grand_total_row = 1
ORDER BY page_number;
"

# Row count per page
sqlite3 output/redbook-20.db -column "
SELECT page_number, COUNT(*) AS rows,
       SUM(CASE WHEN is_total_row THEN 1 ELSE 0 END) AS totals
FROM raw_budget_lines GROUP BY page_number ORDER BY page_number;
"

# Export to CSV for spreadsheet review
sqlite3 output/redbook-20.db -header -csv "
SELECT * FROM raw_budget_lines ORDER BY page_number, id;
" > output/redbook-20.csv
```

### Scale multiplier

Numbers are automatically scaled by the page header's unit (हजार=×1,000, लाख=×100,000, करोड=×10,000,000). A page header reading "रु लाखमा" means all values are stored as real rupees (×100,000). The `verify_budget.py` script and `--sum` flag both compare at the scaled level.

### How it works

1. **Font mapping** — parses 17 ToUnicode CMap tables from the PDF, builds a 120-entry CID→Devanagari lookup
2. **Table detection** — pdfplumber finds table boundaries; for sparse pages (>500 chars, <10 rows), falls back to text-line reconstruction
3. **Row parsing** — token-based regex extraction: first token = budget code, first numeric token = start of numbers, everything between = description
4. **Word sanitizer** — 70-entry known-fix table for broken legacy glyph sequences (पर्देश→प्रदेश, etc.)
5. **Cross-verification** — per (page, section) sum of data rows vs stated total rows, flagged if diff ≥1

---

## Output

All generated files go to `output/` (gitignored):

```
output/
├── notice.png                 OCR: rendered page image
├── notice.html                OCR: positioned HTML overlay
├── notice-ocr.txt             OCR: plain text
├── notice-translated.txt      OCR: English translation
│
├── redbook-20.db              Vector: SQLite database
├── redbook-20.xlsx            Vector: Excel workbook
├── redbook-page{1..20}.csv    Vector: per-page CSV
└── slice-30-50.db             Vector: sliced page range
```

## Project Structure

```
├── pdf_to_text.py          OCR pipeline
├── pdf_to_excel.py         Legacy OCR-to-Excel (baseline)
├── pdf_to_excel_v2.py      Vector pipeline (CID font → SQLite/CSV/Excel)
├── verify_budget.py        Cross-verification script
├── run.sh                  OCR orchestrator
├── Makefile                Budget extraction shortcuts
├── requirements.txt        Dependencies
├── output/                 Generated files (gitignored)
├── dictionary/             Nepali dictionary scripts and text data (tracked)
├── dictionary-data/        Large dictionary binaries (gitignored)
├── ocr-env/                Python venv (gitignored)
└── AGENTS.md               Project conventions & model notes
```

## Known Issues

### OCR
- Some conjuncts and rephas still misrecognized
- PP-OCRv5 Devanagari model must be explicitly specified
- Models cache at `~/.paddlex/official_models/`

### Vector
- Nested subtotals on detail pages (multiple "जम्मा" rows per page) compared individually — each program-level total verified against its own data rows, not page-wide sum
- "स्रोत जम्मा नेपाल" sub-header lines flagged as total rows (no numeric impact)
- Budget codes printed at 3 hierarchy levels (3/5/8-digit) — all present in PDF, no deduplication
- Truncated text at PDF crop boundary (e.g. "राष्ट्रिय प्राकृतिक स्रोत तथा व आयोग")
```

## License

MIT
