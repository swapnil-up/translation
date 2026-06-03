#!/usr/bin/env python
"""
pdf_to_excel_v3.py — PyMuPDF-based extraction for redbook8283.pdf

Uses fitz (PyMuPDF) for text extraction with ToUnicode CMap handling,
then post-processes control characters (unmapped CIDs) using a context-
derived mapping table, and applies word-level fixes for known garbled text.
"""

import argparse
import os
import re
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz

# ── Control char → Devanagari substitution (for unmapped CIDs) ──────
# These CIDs are NOT in the page's ToUnicode CMap, so fitz outputs
# chr(CID) via identity-H fallback. We substitute the correct Unicode.

# Single-character substitutions (CID → single Devanagari codepoint)
CID_CHAR_MAP = {
    # Page 17+ (detail pages) mappings:
    4: '\u0930\u094D',    # CID 4 = र् (ra-halant)
    9: '\u093F',           # CID 9 = ि (vowel sign i)
    14: '\u0935\u093F',   # CID 14 = वि (vi)
    31: '\u092A\u094D\u0930',  # CID 31 = प्र
    33: '\u0926\u093F',   # CID 33 = दि
    39: '\u092E\u094D\u092E',  # CID 39 = म्म
    58: '\u093F',          # CID 58 = ि (vowel sign i, in visual-order)
    59: '\u0935\u093E',   # CID 59 = वा
    60: '\u0940',          # CID 60 = ी (vowel sign ii)
    61: '\u0928\u094D',   # CID 61 = न् (halant na)
    62: '\u0924\u094D\u0924',  # CID 62 = त्त
    6: '\u0938\u094D\u0930',    # CID 6 = स्र
    66: '\u0917\u094D\u0930\u0940',  # CID 66 = ग्री
    68: '\u0943',          # CID 68 = ृ
    69: '\u094D\u092F',   # CID 69 = ्‍य (halant-ya) or व्य
    70: '\u0923\u094D\u0921',  # CID 70 = ण्ड
    72: '\u092D\u094D\u0930',  # CID 72 = भ्र
    75: '\u0942',          # CID 75 = ू
    77: '\u0941\u0939\u0941\u0930\u0941',  # CID 77 = हरू 
    79: '\u0940\u0915\u0943\u0924',  # CID 79 = ीकृत or similar
    80: '\u093F',          # CID 80 = ि (in P1 patterns)
    # Page 35+ (summary pages) mappings:
    12: '\u0928\u094D\u0924',  # CID 12 = न्त
    13: '\u094D\u0924',   # CID 13 = ्त (halant ta)
    16: '\u093F',          # CID 16 = ि
    18: '\u094D\u0930',   # CID 18 = ्र
    24: '\u094D\u0930',   # CID 24 = ्र (same as 18 on page 35)
    34: '\u0938\u094D\u0930',  # CID 34 = स्र (for स्रोत → "ोत)
    35: '\u092E\u094D\u092E',  # CID 35 = म्म (for जम्मा)
    40: '\u0924\u094D\u0924\u093F',  # CID 40 = त्ति
    41: '\u092F\u094D\u092F',  # CID 41 = व्य
    42: '\u0938\u094D\u0925',  # CID 42 = स्थ
}

# Multi-character sequences that need word-level replacement
# (when the grapheme cluster spans multiple CIDs)
WORD_FIXES = {
    '\x1f\x09\x24\x09\x6e\x09\xe7': 'प्रतिनिधि',  # CID 31,9,36,9,110,9,231
    'म\x0c\rालय': 'मन्त्रालय',
    '\x10नवा\x18चन': 'निर्वाचन',
    '\x10नकाय': 'निकाय',
    'अि\tतयार': 'अनुसन्धान',  
    'अनुस\x0cधान': 'अनुसन्धान',
}

# Pre-compose known garbled words (exact replacements)
# These handle cases where multiple CIDs interact
EXACT_FIXES = {
    'शीष\x04क': 'शीर्षक',
    '\x06ोत': 'स्रोत',
    'यथाथ\x04': 'यथार्थ',
    'खच\x04': 'खर्च',
    'संशो\tधत': 'संशोधित',
    '\x1fाथ\tमकता': 'प्राथमिकता',
    '!दगो': 'दिगो',
    '\x0eवकास': 'विकास',
    'लै\tगंक': 'लैङ्गिक',
    "ज'मा": 'जम्मा',
    'रा9प\tत': 'राष्ट्रपति',
    'पा:र;\tमक': 'पारिवारिक',
    'पदा\tधकार<': 'पदाधिकारी',
    'अ=य': 'अन्य',
    'सु\tबधा': 'सुविधा',
    'भ>ा': 'भत्ता',
    'इ=धन': 'इन्धन',
    'काया\x04लय': 'कार्यालय',
    'सामाBी': 'सामग्री',
    '\x1fयोजन': 'प्रयोजन',
    '\x0eविशD': 'विशिष्ट',
    '1यिE': 'व्यक्ति',
    '\x1f\tत\tन\tध': 'प्रतिनिधि',
    'मFडल': 'मण्डल',
    'Hमण': 'भ्रमण',
    '\x0eव\x0eवध': 'विविध',
    'उपरा9प\tत': 'उपराष्ट्रपति',
    'सवार<': 'सवारी',
    'मम\x04त': 'मर्मत',
    'मूKयांकन': 'मूल्यांकन',
    '\x1fदेश': 'प्रदेश',
    '\x1fमुखहM': 'प्रमुखहरू',
    'एकOकृत': 'एकीकृत',
    '\x0eव>ीय': 'वित्तीय',
    'मा\tथ': 'माथि',
    '1ययभार': 'व्ययभार',
    '1याज': 'व्याज',
    'रा\x0e9य': 'राष्ट्रिय',
    'क\tमशन': 'कमिशन',
    'अथ\x04': 'अर्थ',
    'म=[ालय': 'मन्त्रालय',
    'भुEानी': 'भुक्तानी',
    'बहुपZीय': 'बहुपक्षीय',
    '`याज': 'व्याज',
    'एिशयाल<': 'एशियाली',
    '\x0e9य': 'ाष्ट्रिय',  # part of राष्ट्रिय
    'अ=तरा\x04\x0e9य': 'अन्तर्राष्ट्रिय',
    'कृ\x0eष': 'कृषि',
    'न\tड\x04क': 'निडिक',
    'बbक': 'बैंक',
    'इ=भेDमेFट': 'इन्भेस्टमेण्ट',
    'युरो\x0eपयन': 'युरोपियन',
    'ए.आइ.आइ.\x0eव.': 'ए.आइ.आइ.वि.',
    'मुdा': 'मुद्रा',
    '!eपZीय': 'द्विपक्षीय',
    '\x10धकार': 'अधिकार',
    'अनुस\x0cधान': 'अनुसन्धान',
    '\x0cयाय': 'न्याय',
    'प@रषB': 'परिषद',
    '8ाकृ\x10तक': 'प्राकृतिक',
    '8देश': 'प्रदेश',
    '8मुखह:': 'प्रमुखहरू',
    'रा\x1f1य': 'राष्ट्रिय',
    'अ\x10धकार': 'अधिकार',
    'सिDत': 'सञ्चित',
    ')यय': 'व्यय',
    'िनकासा': 'विवरण',
    'मसल=द': 'मसलन्द',
    'सवार<': 'सवारी',
    'मेिशनर<': 'मेसिनरी',
    "स'पि>": 'सम्पत्तिको',
    'स0ालन': 'सञ्चालन',
    'गFडकO': 'गण्डकी',
    'िFडकल': 'गण्डकी',
    'ि0त': 'ञ्चित',
    'स0चार': 'सञ्चार',
    '0योजना': 'वियोजना',
    'ि0योजना': 'विनियोजना',
    'ि0मय': 'निर्मय',
    'वैदेिशक': 'वैदेशिक',
    'ि0चार': 'सञ्चार',
    'िकया': 'किया',  
    'भएगएको': 'भए गएको',
    'रपोट': 'रिपोर्ट',
    'पर=>कको': 'परीक्षकको',
    'वविकास': 'विविध',
    'िFडकल': 'गण्डकी',
    "िस'चार": 'सञ्चार',
    "स'चार": 'सञ्चार',
    'वैदेिशक': 'वैदेशिक',
    'भ@ा': 'भत्ता',
    'कमर्चार>': 'कर्मचारी',
    'बैठक भ@ा': 'बैठक भत्ता',
    'प्रो^साहन': 'प्रोत्साहन',
    'पुर3कार': 'पुरस्कार',
    'अBय': 'अन्य',
    'सवार>': 'सवारी',
    'मेिशनर>': 'मेसिनरी',
    'धा<रत': 'धारित',
    'सुर_ा': 'सुरक्षा',
    'सामाIी': 'सामग्री',
    'पु3तक': 'पुस्तक',
    'शुOक': 'शुल्क',
    "स'पि@": 'सम्पत्ति',
    "स'भार": 'सम्भार',
    "स'चालन": 'सञ्चालन',
    'िFडकल': 'गण्डकी',
    'पKपिKका': 'पत्रपत्रिका',
    'विफXचसर्': 'विफर्निचर',
    "क'`युटर": 'कम्प्युटर',
    'सZटवेयर': 'सफ्टवेयर',
    'खर>द': 'खरीद',
    'सामाIी': 'सामग्री',
    'ि@को': 'त्तिको',
    '@को': 'त्तिको',
    'इBधन': 'इन्धन',
    'सामािजक': 'सामाजिक',
    'िनवृ@': 'निवृत्त',
    'नवीकरण': 'नवीकरण',
    'कमर्चार>को': 'कर्मचारीको',
    'कमर्चार>': 'कर्मचारी',
    'प्रो^साहन': 'प्रोत्साहन',
    'िबजुल>': 'बिजुली',
    'सवार>': 'सवारी',
    'मसलBद': 'मसलन्द',
    'सम्पत्तिहH': 'सम्पत्तिहरू',
    'िवभागहH': 'विभागहरू',
    'प्रणाल>': 'प्रणाली',
    'सामIी': 'सामग्री',
    'परामशर्': 'परामर्श',
    'िकया': 'किया',
    'रपोट': 'रिपोर्ट',
    'अBय': 'अन्य',
    'इBधन': 'इन्धन',
    'खर>द': 'खरीद',
    'पु3तक': 'पुस्तक',
    'शुOक': 'शुल्क',
    "स'पi@": 'सम्पत्ति',
    "स'पि>को": 'सम्पत्तिको',
}

# ── Constants ────────────────────────────────────────────────────────
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
DIGIT_MAP = str.maketrans("०१२३४५६७८९", "0123456789")
TOTAL_KEYWORDS = {"जम्मा", "कुल", "जोड", "कूल", "योग"}
SCALE_PATTERNS = [
    (re.compile(r'हजार', re.UNICODE), 1000),
    (re.compile(r'लाख', re.UNICODE), 100_000),
    (re.compile(r'करोड', re.UNICODE), 10_000_000),
]


# ── Post-processing ──────────────────────────────────────────────────

def fix_text(text: str) -> str:
    """Apply CID→Unicode mapping and word-level fixes."""
    # 1. Apply exact word fixes first (longest match wins)
    for broken, correct in sorted(EXACT_FIXES.items(), key=lambda x: -len(x[0])):
        text = text.replace(broken, correct)
    
    # 2. For remaining control chars, apply CID mapping
    chars = []
    for c in text:
        if ord(c) < 32 and ord(c) != 10:  # control char (not newline)
            cid = ord(c)
            if cid in CID_CHAR_MAP:
                chars.append(CID_CHAR_MAP[cid])
            else:
                chars.append(f'[{cid}]')
        else:
            chars.append(c)
    
    result = ''.join(chars)
    
    # 3. Apply EXACT_FIXES again (post-CID: now patterns like "कमर्चार>को" work since \x04→र्)
    for old, new in sorted(EXACT_FIXES.items(), key=lambda x: -len(x[0])):
        result = result.replace(old, new)
    
    # 4. Clean up any remaining [CID:N] placeholders
    result = re.sub(r'\[\d+\]', '', result)
    
    return result


def sanitize_devanagari(text: str) -> str:
    """Clean basic extraction artifacts. Preserves newlines."""
    text = text.replace('\ufffd', '')
    lines = []
    for line in text.split('\n'):
        line = re.sub(r'\s+', ' ', line).strip()
        if line:
            lines.append(line)
    return '\n'.join(lines)


def parse_number(text: str) -> Optional[float]:
    """Parse a Nepali number string (with comma as thousands sep)."""
    text = text.strip()
    text = text.translate(DIGIT_MAP)
    text = re.sub(r'[^\d,.-]', '', text)
    if not text:
        return None
    try:
        text = text.replace(',', '')
        return float(text)
    except ValueError:
        return None


# ── Page text extraction ─────────────────────────────────────────────

def extract_page_text(doc, pno: int) -> str:
    """Extract text from a single page using PyMuPDF."""
    page = doc[pno]
    text = page.get_text('text')
    return text


def detect_scale(text: str) -> int:
    """Detect budget scale (हजार/लाख/करोड) from page text."""
    for pattern, multiplier in SCALE_PATTERNS:
        if pattern.search(text):
            return multiplier
    return 1


# ── Table row parsing ───────────────────────────────────────────────

@dataclass
class BudgetRow:
    code: str = ''
    description: str = ''
    year_actual: float = 0
    year_revised: float = 0
    year_estimate: float = 0
    total: float = 0
    current_exp: float = 0
    capital_exp: float = 0
    financial: float = 0
    baideshik_anudan: float = 0
    baideshik_rin: float = 0
    prathamikta_sanket: str = ''
    raniti_sanket: str = ''
    laigik_sanket: str = ''
    is_total: bool = False
    page: int = 0


BUDGET_CODE_RE = re.compile(r'^(\d{3,15})')
AMOUNT_RE = re.compile(r'[\d,]+')


# ── State-machine parser ─────────────────────────────────────────────

HEADER_KEYWORDS = ['शीर्षक', 'स्रोत', 'अनुदान', 'विवरण', 'यथार्थ', 'संशोधित',
                   'प्राथमिकता', 'दिगो', 'लैङ्गिक', 'नेपाल सरकार', 'वैदेशिक',
                   'संघीय', 'व्ययभार', 'आर्थिक', 'बजेट']
AMOUNT_LINE_RE = re.compile(r'^[\d,.\-]+$')
DESC_CONTINUE_KEYWORDS = ['नेपाल सरकार', 'नगद', 'कार्यालय', 'सामग्री', 'खर्च',
                          'भत्ता', 'सुविधा', 'मर्मत', 'इन्धन', 'पोशाक',
                          'पानी', 'संचार', 'महसुल', 'वीमा', 'नवीकरण',
                          'औजार', 'भ्रमण', 'अनुगमन', 'मूल्यांकन', 'साधन',
                          'सवारी', 'मेसिनरी']

# Year labels like "2080/81 को" should not be treated as budget codes
YEAR_LABEL_RE = re.compile(r'^\d{4}/\d{2}')
# Real budget codes: 3+ digits, not a year, not just the year
BUDGET_CODE_VALID_RE = re.compile(r'^(\d{3,15})$')

def process_page_lines(lines: list[str], page: int, scale: int) -> list[BudgetRow]:
    rows = []
    current_code = ''
    current_desc_parts = []
    current_amounts: list[float] = []
    current_total = False
    current_priority_code = ''
    current_raniti = ''
    current_laigik = ''
    
    def finalize_current():
        nonlocal current_code, current_desc_parts, current_amounts, current_total
        nonlocal current_priority_code, current_raniti, current_laigik
        if not current_code and not current_total:
            return
        desc = ' '.join(current_desc_parts).strip()
        row = BudgetRow(
            code=current_code,
            description=desc,
            page=page,
            is_total=current_total,
        )
        if current_priority_code:
            row.prathamikta_sanket = current_priority_code
            row.raniti_sanket = current_raniti
            row.laigik_sanket = current_laigik
        if current_amounts:
            amounts = [a * scale for a in current_amounts]
            n = len(amounts)
            row.year_actual = amounts[0] if n >= 1 else 0
            row.year_revised = amounts[1] if n >= 2 else 0
            row.year_estimate = amounts[2] if n >= 3 else 0
            row.total = amounts[3] if n >= 4 else 0
            row.current_exp = amounts[4] if n >= 5 else 0
            row.capital_exp = amounts[5] if n >= 6 else 0
            row.financial = amounts[6] if n >= 7 else 0
            row.baideshik_anudan = amounts[7] if n >= 8 else 0
            row.baideshik_rin = amounts[8] if n >= 9 else 0
        rows.append(row)
    
    def is_amount_line(s: str) -> bool:
        s = s.strip()
        if not s:
            return False
        return bool(re.match(r'^[\d,.\-]+$', s))
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        
        # Skip header keywords
        stripped = line.replace(' ', '')
        if any(stripped.startswith(kw.replace(' ', '')) for kw in HEADER_KEYWORDS):
            continue
        
        # Skip year labels
        if YEAR_LABEL_RE.match(line):
            continue
        
        # Skip "खर्च" / "जम्मा" sub-headers that are just text
        if line in ('खर्च', 'जम्मा'):
            continue
        
        # Check for total
        is_total = any(kw in line for kw in TOTAL_KEYWORDS)
        
        # Try to extract a budget code from the start of the line
        # Only match pure digit sequences (no commas, slashes)
        code_match = None
        m = re.match(r'^(\d{3,15})\b', line)
        if m:
            code_candidate = m.group(1)
            # Verify it's a valid budget code (not "2080" from "2080/81 को")
            if not re.match(r'^\d{4}$', code_candidate):  # not a 4-digit year
                code_match = m
            elif i < len(lines) and not lines[i].strip().startswith('/'):
                code_match = m
        
        if code_match:
            finalize_current()
            code = code_match.group(1)
            rest = line[code_match.end():].strip()
            current_code = code
            current_desc_parts = [rest] if rest else []
            current_amounts = []
            current_total = is_total
            current_priority_code = ''
            current_raniti = ''
            current_laigik = ''
            continue
        
        # Handle "P1", "0", "3" as priority codes on separate lines
        if re.match(r'^P\d+$', line) and current_code:
            current_priority_code = line[1:]  # "1" from "P1"
            # Look ahead for raniti and laigik single digits
            j = i
            while j < len(lines):
                next_line = lines[j].strip()
                if re.match(r'^\d$', next_line):
                    if not current_raniti:
                        current_raniti = next_line
                    elif not current_laigik:
                        current_laigik = next_line
                    else:
                        break
                    j += 1
                    i = j  # skip consumed lines
                else:
                    break
            continue
        
        # If we're in a row
        if current_code:
            # Check if this line is amount-like
            if is_amount_line(line):
                n = parse_number(line)
                if n is not None:
                    current_amounts.append(n)
                    continue
            
            # Check if this is a description continuation
            if any(kw in line for kw in DESC_CONTINUE_KEYWORDS):
                current_desc_parts.append(line)
                continue
            
            # If we have amounts and hit a non-amount, non-desc line, finalize
            if current_amounts:
                finalize_current()
                current_code = ''
                current_desc_parts = []
                current_amounts = []
                current_total = False
                # Re-process this line in next iteration... but we already consumed it
                # Let the next iteration handle it as standalone logic
            continue
        
        # Not in a row
        if is_total:
            n = parse_number(line)
            if n is not None:
                row = BudgetRow(is_total=True, page=page, total=n * scale)
                rows.append(row)
            else:
                current_code = ''
                current_desc_parts = []
                current_amounts = []
                current_total = True
            continue
        
        # Skip random standalone numbers (no active code)
        if is_amount_line(line):
            continue
    
    finalize_current()
    return rows


# ── Main extraction ──────────────────────────────────────────────────

def extract_pdf(pdf_path: str, max_pages: Optional[int] = None,
                db_path: Optional[str] = None):
    """Extract budget data from PDF and write to SQLite."""
    
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    if max_pages:
        total_pages = min(total_pages, max_pages)
    
    all_rows = []
    # Track cumulative scale across pages - continuation pages inherit from first detail page
    current_scale = 1
    first_detail_page = None
    
    for pno in range(total_pages):
        sys.stderr.write(f'\rPage {pno+1}/{total_pages}')
        sys.stderr.flush()
        
        # Extract and fix text
        raw_text = extract_page_text(doc, pno)
        fixed_text = fix_text(raw_text)
        fixed_text = sanitize_devanagari(fixed_text)
        
        # Detect scale - page may not have explicit marker if it's a continuation
        page_scale = detect_scale(fixed_text)
        if page_scale != 1 or first_detail_page is None:
            current_scale = page_scale
        if page_scale != 1 and first_detail_page is None:
            first_detail_page = pno
        
        # Get lines
        lines = fixed_text.split('\n')
        
        # Process with state machine
        rows = process_page_lines(lines, pno + 1, current_scale)
        all_rows.extend(rows)
    
    sys.stderr.write('\n')
    
    # Output stats
    n_codes = sum(1 for r in all_rows if r.code)
    n_totals = sum(1 for r in all_rows if r.is_total)
    print(f'Extracted {len(all_rows)} rows ({n_codes} with codes, {n_totals} totals)',
          file=sys.stderr)
    
    # Write to SQLite
    if db_path:
        _write_sqlite(all_rows, doc, db_path)
    
    return all_rows


def _write_sqlite(rows, doc, db_path: str):
    """Write extracted rows to SQLite database."""
    import sqlite3
    
    # Remove existing file
    if os.path.exists(db_path):
        os.remove(db_path)
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS budget (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page INTEGER,
            code TEXT,
            description TEXT,
            year_actual REAL,
            year_revised REAL,
            year_estimate REAL,
            total REAL,
            current_exp REAL,
            capital_exp REAL,
            financial REAL,
            baideshik_anudan REAL,
            baideshik_rin REAL,
            prathamikta_sanket TEXT,
            raniti_sanket TEXT,
            laigik_sanket TEXT,
            is_total INTEGER DEFAULT 0
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pages (
            page INTEGER PRIMARY KEY,
            content TEXT
        )
    ''')
    
    for row in rows:
        cur.execute('''
            INSERT INTO budget (
                page, code, description, year_actual, year_revised,
                year_estimate, total, current_exp, capital_exp, financial,
                baideshik_anudan, baideshik_rin, prathamikta_sanket,
                raniti_sanket, laigik_sanket, is_total
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            row.page, row.code, row.description,
            row.year_actual, row.year_revised, row.year_estimate,
            row.total, row.current_exp, row.capital_exp, row.financial,
            row.baideshik_anudan, row.baideshik_rin,
            row.prathamikta_sanket, row.raniti_sanket, row.laigik_sanket,
            1 if row.is_total else 0
        ))
    
    # Store page content
    for pno in range(len(doc)):
        page = doc[pno]
        text = fix_text(extract_page_text(doc, pno))
        cur.execute('INSERT OR REPLACE INTO pages (page, content) VALUES (?, ?)',
                    (pno + 1, text))
    
    conn.commit()
    conn.close()
    print(f'Wrote {len(rows)} rows to {db_path}', file=sys.stderr)


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Extract Nepali budget PDF using PyMuPDF')
    parser.add_argument('pdf', help='Path to PDF file')
    parser.add_argument('--max-pages', type=int, help='Max pages to process')
    parser.add_argument('--sqlite', action='store_true', help='Output to SQLite')
    parser.add_argument('--output', '-o', help='Output path')
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf):
        print(f'Error: {args.pdf} not found', file=sys.stderr)
        sys.exit(1)
    
    output_path = args.output
    if not output_path and args.sqlite:
        base = os.path.splitext(os.path.basename(args.pdf))[0]
        output_path = f'output/{base}.db'
    
    rows = extract_pdf(args.pdf, max_pages=args.max_pages, db_path=output_path)
    
    # Print sample
    for r in rows[:10]:
        print(f'  {r.page:3d} | {r.code:10s} | {r.description[:30]:30s} | '
              f'{r.year_actual:>10.0f} | {r.total:>10.0f}')
    if len(rows) > 10:
        print(f'  ... ({len(rows)} total rows)')


if __name__ == '__main__':
    main()
