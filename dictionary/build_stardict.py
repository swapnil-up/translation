#!/usr/bin/env python3
"""Generate StarDict (.ifo, .idx, .dict) from nep_dict.sqlite3."""

import sqlite3
import struct
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "dictionary-data" / "nep_dict.sqlite3"
OUT_DIR = Path(__file__).parent.parent / "dictionary-data"

BOOK_NAME = "Nepali Contemporary Dictionary"
AUTHOR = "Karl-Heinz Krämer / OpenCorpus Nepal"


def build_stardict():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    cur.execute("""
        SELECT w.value, GROUP_CONCAT(d.value, '\n')
        FROM word w
        LEFT JOIN definition d ON w.id = d.word_id
        GROUP BY w.id
        ORDER BY w.value
    """)
    rows = cur.fetchall()
    conn.close()

    print(f"Loaded {len(rows)} entries")

    dict_data = b""
    idx_entries = bytearray()
    offset = 0

    for word, defs_raw in rows:
        if not defs_raw:
            defs_raw = "(no definition)"
        entry_text = f"{defs_raw}\n"
        entry_bytes = b"h" + entry_text.encode("utf-8")
        dict_data += entry_bytes

        word_bytes = word.encode("utf-8") + b"\0"
        idx_entries += word_bytes
        idx_entries += struct.pack(">II", offset, len(entry_bytes))
        offset += len(entry_bytes)

    idx_path = OUT_DIR / "nepali_dictionary.idx"
    idx_path.write_bytes(bytes(idx_entries))

    dict_path = OUT_DIR / "nepali_dictionary.dict"
    dict_path.write_bytes(dict_data)

    ifo_path = OUT_DIR / "nepali_dictionary.ifo"
    ifo_path.write_text(
        f"""StarDict's dict ifo file
version=3.0.0
bookname={BOOK_NAME}
wordcount={len(rows)}
idxfilesize={len(idx_entries)}
author={AUTHOR}
description=Nepali-English bilingual dictionary
date=2025.05.25
""",
        encoding="utf-8",
    )

    print(f".ifo:  {ifo_path}")
    print(f".idx:  {idx_path}  ({len(idx_entries)} bytes)")
    print(f".dict: {dict_path}  ({len(dict_data)} bytes)")
    print(f"\nEntries: {len(rows)}")


if __name__ == "__main__":
    build_stardict()
