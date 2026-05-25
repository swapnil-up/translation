#!/usr/bin/env python3
"""
Merge bilingual pairs from eng_nep_pairs.txt into nep_dict.sqlite3.

For each line:
  english_side \t devanagari_word
- If devanagari_word already exists in `word` table → append english_side as a new definition
- If not → create new word entry with english_side as its first definition
"""

import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PAIRS_PATH = SCRIPT_DIR / "eng_nep_pairs.txt"
DB_PATH = SCRIPT_DIR.parent / "dictionary-data" / "nep_dict.sqlite3"


def get_next_id(cur, table: str) -> int:
    cur.execute(f"SELECT COALESCE(MAX(id), 0) + 1 FROM {table}")
    return cur.fetchone()[0]


def main():
    if not PAIRS_PATH.exists():
        print(f"Error: {PAIRS_PATH} not found"); sys.exit(1)
    if not DB_PATH.exists():
        print(f"Error: {DB_PATH} not found"); sys.exit(1)

    pairs = []
    for line in PAIRS_PATH.read_text(encoding="utf-8").splitlines():
        if "\t" not in line:
            continue
        en, ne = line.strip().split("\t", 1)
        if ne:
            pairs.append((en.strip(), ne.strip()))

    print(f"Loaded {len(pairs)} bilingual pairs")

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    new_words = 0
    new_defs = 0
    skipped = 0

    for en, ne in pairs:
        if not en or not ne:
            skipped += 1
            continue

        cur.execute("SELECT id FROM word WHERE value = ?", (ne,))
        row = cur.fetchone()

        if row:
            word_id = row[0]
        else:
            word_id = get_next_id(cur, "word")
            cur.execute(
                "INSERT INTO word (id, value, part_of_speech) VALUES (?, ?, ?)",
                (word_id, ne, "N/A"),
            )
            new_words += 1

        def_id = get_next_id(cur, "definition")
        cur.execute(
            "INSERT INTO definition (id, word_id, value) VALUES (?, ?, ?)",
            (def_id, word_id, en),
        )
        new_defs += 1

    conn.commit()
    conn.close()

    print(f"New words created: {new_words}")
    print(f"New definitions added: {new_defs}")
    print(f"Skipped (empty): {skipped}")
    print(f"Total words in DB now: {new_words + 7530}")


if __name__ == "__main__":
    main()
