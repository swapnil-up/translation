# Nepali Admin Copilot — OCR Slice

Extract clean Devanagari Unicode text from Nepali government PDFs that use legacy font sets (Preeti, Kantipur), then optionally translate to English via Gemini.

## Quick Start

```bash
uv venv ocr-env --python 3.10
uv pip install --python ocr-env/bin/python -r requirements.txt setuptools

# Plain OCR to stdout
ocr-env/bin/python pdf_to_text.py notice.pdf

# HTML overlay — text positioned on top of the document image
ocr-env/bin/python pdf_to_text.py notice.pdf --html

# Translate to English via Gemini 2.5 Flash Lite
export GEMINI_API_KEY='your-key'
ocr-env/bin/python pdf_to_text.py notice.pdf --translate

# Full pipeline: HTML + translation
ocr-env/bin/python pdf_to_text.py notice.pdf --html --translate
```

Or use the orchestrator:

```bash
./run.sh notice.pdf               # Plain OCR
./run.sh notice.pdf --save        # Save to output/notice-ocr.txt
./run.sh notice.pdf --html        # HTML overlay
./run.sh notice.pdf --translate   # Translate
./run.sh notice.pdf --all         # HTML + translate, opens browser
```

First run downloads model weights (~80 MB). Subsequent runs are cached.

## HTML Overlay Features

- **Hover zoom** — hover any line to see it enlarged with word-wrap (no horizontal scrolling)
- **Bilingual** — when `--translate` is used, English appears in yellow below the Devanagari
- **Responsive** — scales with the browser window

## Output

All generated files go to `output/` (gitignored):

```
output/
├── notice.png              Rendered PDF page (300 DPI)
├── notice.html             Positioned HTML overlay
├── notice-ocr.txt          Plain OCR text
└── notice-translated.txt   English translation (when --translate)
```

## How it works

1. **PDF → Image** — renders at 300 DPI via `pdf2image` (poppler), flattening legacy fonts to pixels
2. **Image → Unicode** — PaddleOCR (PP-OCRv5) with `devanagari_PP-OCRv5_mobile_rec` model
3. **Filter** — discards low-confidence and non-Devanagari detections
4. **Translate** — pipes OCR text through Gemini 2.5 Flash Lite with a government-terminology glossary

## Known Issues

- Some conjuncts and rephas (half-letters) still misrecognized
- PP-OCRv5 Devanagari model must be explicitly specified (not the default multilingual model)
- Models cache at `~/.paddlex/official_models/` — delete when switching paddlepaddle versions

## Project Structure

```
├── pdf_to_text.py       Main OCR pipeline
├── requirements.txt     Dependencies
├── run.sh               Orchestrator script
├── notice.pdf           Sample test document
├── output/              Generated files (gitignored)
├── dictionary/          Nepali dictionary scripts and text data (tracked)
│   ├── nepDict.py               SQLite → DSL converter
│   ├── dsl-parser.py            English-Nepali pair extractor
│   ├── eng_nep_pairs.txt        3,800+ bilingual word pairs
│   └── ...
├── dictionary-data/     Large dictionary binaries (gitignored)
│   ├── nep_dict.sqlite3         7,620 word dictionary DB
│   ├── nepali_dictionary.dsl    DSL format (KOReader-compatible)
│   └── nepali_dictionary.{dict,idx,syn}  StarDict format
├── ocr-env/             Python venv (gitignored)
└── AGENTS.md            Project conventions & model notes
```

## License

MIT
