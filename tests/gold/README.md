# Gold Standard Test Set

The gold pages are the **ground truth** for the redbook extraction: every value
is hand-transcribed from `redbook8283.pdf` by a human. Nothing in the pipeline
is trusted until it matches these pages. See STRATEGY.md §7.

## How a gold page is made

1. Run extraction on a page range and open the SQLite DB:
   ```bash
   python redbook_parser/cli.py extract output/redbook8283.pdf \
       --start-page 17 --max-pages 1 --sqlite -o output/page-17.db
   ```
2. Seed a draft from the DB (so you edit, not retype):
   ```bash
   python tests/gold/record_gold.py output/page-17.db 17
   # writes tests/gold/pages/page_017.json with verified: false
   ```
3. Open the PDF at that page in a viewer, and **check every row against the
   PDF by hand**. Fix codes, descriptions, amounts, scale, totals, and the
   `template` field. A gold page is only useful if the numbers are right.
4. Set `"verified": true` in the JSON when you're confident, and flip the
   manifest entry for that page from `todo` to `done`.
5. `tests/test_gold.py` then compares the pipeline output for that page
   against the JSON, field by field. It only runs for pages with
   `status: done` AND the PDF present.

## Schema (`tests/gold/pages/page_<NNN>.json`)

```json
{
  "pdf": "redbook8283.pdf",
  "page": 17,
  "scale": 100000,
  "template": "detail",
  "verified": false,
  "notes": "",
  "rows": [
    {
      "code": "111111",
      "description": "अर्थ मन्त्रालय कार्यालय",
      "year_actual": 1230000,
      "year_revised": 0,
      "year_estimate": 0,
      "total": 1230000,
      "current_exp": 0,
      "capital_exp": 0,
      "financial": 0,
      "baideshik_anudan": 0,
      "baideshik_rin": 0,
      "prathamikta_sanket": "",
      "raniti_sanket": "",
      "laigik_sanket": "",
      "is_total": false,
      "row_type": "budget"
    }
  ]
}
```

Rules:

- **Amounts are FINAL scaled values** (already × `scale`), matching what the
  pipeline writes. Store them as JSON numbers; `record_gold.py` converts the
  DB's REAL values.
- **Code, description, and all 12 columns** must match the PDF, not the DB.
  The DB is a draft with known bugs; the PDF is truth.
- **Every data row that visibly exists on the page should be present.**
  `test_gold.py` requires a 1:1 match in both directions — a gold page with
  rows the parser still drops (the known bugs in STRATEGY.md §5) will fail
  until those bugs are fixed, which is the point.
- Total rows: `"is_total": true`, `row_type` stays `"budget"` (v3 uses the
  `is_total` flag; `row_type: "heading"` is only for section headings).

## Reference

- Target pages and why: `manifest.json`
- Recorder tool: `record_gold.py` (`python tests/gold/record_gold.py --help`)
- Comparator: `test_gold.py`
