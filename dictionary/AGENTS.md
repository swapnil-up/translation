# AGENTS.md — Dictionary

## Pipeline
- `extract_pairs.py` — OCRs nep-eng.pdf with column-aware parser, produces 4,263 bilingual pairs
- `nepDict.py` — SQLite → DSL converter for KOReader
- `build_stardict.py` — SQLite → StarDict converter for sdcv
- `merge_pairs.py` — merges bilingual pairs into nep_dict.sqlite3

## Running
```bash
# sdcv lookup (from repo root)
STARDICT_DATA_DIR="dictionary-data" sdcv "अभाव"

# Regenerate DSL from SQLite
ocr-env/bin/python dictionary/nepDict.py --convert dictionary-data/nep_dict.sqlite3 -o dictionary-data/nepali_dictionary.dsl

# Regenerate StarDict from SQLite
ocr-env/bin/python dictionary/build_stardict.py
```

## Known Issues
- `sdcv -u` flag causes "Internal error: map::at" — use interactive mode or omit `-u`
- StarDict `.dict.dz` breaks sdcv 0.5.2 — always remove; plain `.dict` works
- 57% of bilingual pairs don't match existing DB headwords due to OCR spelling diffs, multi-word phrases, and new vocabulary
- PP-OCRv5 common errors: ब/व confusion, missing anusvara, conjunct simplification
- If re-extracting pairs, delete `.progress` file to restart from beginning (not resume)

## Conventions
- `dictionary/` tracked — scripts + text data (eng_nep_pairs.txt)
- `dictionary-data/` gitignored — binaries (SQLite, DSL, StarDict, source PDF)
- eng_nep_pairs.progress deleted after commit (resume artifact)
