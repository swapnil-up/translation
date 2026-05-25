#!/usr/bin/env python3
"""
Extract English/Nepali word pairs from OCR text.
- Last ASCII (Roman/English) line → next Devanagari line
- Skip blank lines
- Ignore extra columns for now
"""

import re

DEVANAGARI_RE = re.compile(r'[\u0900-\u097F]')

input_file = 'dict.txt'   # your OCR text file
output_file = 'eng_nep_pairs.txt'

lines = [line.rstrip() for line in open(input_file, encoding='utf-8')]

last_roman = ''
pairs = []

for line in lines:
    stripped = line.strip()
    if not stripped:
        continue  # skip blank lines

    if DEVANAGARI_RE.search(stripped):
        if last_roman:
            pairs.append(f"{last_roman}\t{stripped}")
    else:
        # line without Devanagari → treat as Roman/English headword
        # optional: ignore long lines that are probably gloss
        if len(stripped) <= 50:
            last_roman = stripped

# Write output
with open(output_file, 'w', encoding='utf-8') as f:
    f.write("\n".join(pairs))

print(f"Extracted {len(pairs)} English/Nepali pairs → {output_file}")
