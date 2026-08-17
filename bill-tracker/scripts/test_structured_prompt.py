"""
Test: Gemini structured JSON extraction from a single already-OCR'd notice.

Sends the Devanagari OCR text to Gemini with a JSON schema prompt.
Returns both the full translation + structured metadata in one response.

Usage:
    export GEMINI_API_KEY='key'
    python scripts/test_structured_prompt.py translations/Notice_2083-03-31-ocr.txt

Compares output with existing freeform translation at translations/Notice_2083-03-31.txt
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models"

_SCHEMA_DESC = """
- full_translation_en: The complete English translation of the entire document as a single narrative string. Preserve all names, dates, numbers, and bill references exactly.
- session.date_bs: Nepali date (e.g. 2081-04-12)
- session.date_ad: Approximate AD date if inferrable, else null
- session.meeting_type: Type of session (e.g. House of Representatives, Zero Hour, Special Time)
- session.meeting_number: Meeting/sitting number if mentioned
- session.chairperson: Name of presiding officer
- sections[].name: Section name (e.g. Opening, Impromptu Session, Zero Hour, Main Business, Adjournment)
- sections[].summary_en: 1-3 sentence summary of what happened in this section
- sections[].speakers[].name: Full name of the MP or minister
- sections[].speakers[].party: Party abbreviation if mentioned, else null
- sections[].speakers[].topic: What they spoke about in 5-10 words
- sections[].bills_discussed[].name: Full bill name
- sections[].bills_discussed[].status: introduced | discussed | passed | ratified | sent_to_committee
- sections[].reports_presented[]: Report names if any
- sections[].key_issues[]: Key issues/topics raised in this section
- agenda_tags[]: 5-15 freeform topical keywords for searching across notices
- ministries_mentioned[]: Ministry names referenced
- all_speakers_mentioned[].name: Speaker name
- all_speakers_mentioned[].party: Party if mentioned
- all_speakers_mentioned[].section: Which section they appeared in
- adjournment_time: Time of adjournment if mentioned
- next_meeting_date: Next meeting date if announced
"""

STRUCTURED_PROMPT = """You are an expert translator of Nepali parliamentary documents.

Translate the following Nepali Devanagari OCR text from a House of Representatives meeting notice into English.

Return a JSON object with exactly this structure — no markdown, no code fences, pure JSON:{schema}
Rules:
- full_translation_en must be the COMPLETE translation. Do not summarize or truncate it.
- All names, dates, amounts, and bill references must be preserved exactly.
- speakers lists per section: include every named MP or minister who spoke.
- If a party is not explicitly stated in text, set to null.
- agenda_tags: extract 5-15 topical keywords that would help someone search for this notice later.
- If a field has no data, use null or empty array — never omit the field.
- Output valid JSON only.

--- BEGIN OCR TEXT ---
{ocr_text}
--- END OCR TEXT ---"""


def load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def call_gemini_structured(ocr_text: str, api_key: str) -> dict:
    prompt = STRUCTURED_PROMPT.format(schema=_SCHEMA_DESC, ocr_text=ocr_text)

    resp = requests.post(
        f"{GEMINI_API}/{GEMINI_MODEL}:generateContent",
        headers={"Content-Type": "application/json"},
        params={"key": api_key},
        json={
            "system_instruction": {
                "parts": [{"text": "You are an expert translator of Nepali parliamentary documents. Output JSON only."}]
            },
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.2,
                "maxOutputTokens": 16384,
            },
        },
    )

    if not resp.ok:
        err = resp.json().get("error", {}).get("message", resp.text[:500])
        raise RuntimeError(f"Gemini API error: {err}")

    candidates = resp.json().get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError("Gemini returned empty content")

    text = parts[0].get("text", "").strip()
    return json.loads(text)


def main():
    load_env()

    parser = argparse.ArgumentParser(description="Test structured Gemini extraction on one OCR'd notice")
    parser.add_argument("ocr_file", help="Path to the Devanagari OCR .txt file")
    parser.add_argument("--output", "-o", help="Save structured JSON result to this path")
    parser.add_argument("--compare", help="Path to existing English translation .txt for comparison")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    ocr_path = Path(args.ocr_file)
    if not ocr_path.exists():
        print(f"Error: {ocr_path} not found", file=sys.stderr)
        sys.exit(1)

    ocr_text = read_file(ocr_path)
    print(f"[input] {ocr_path.name} — {len(ocr_text)} chars", file=sys.stderr)

    print(f"[gemini] sending to {GEMINI_MODEL}...", file=sys.stderr)
    result = call_gemini_structured(ocr_text, api_key)
    print(f"[gemini] response received", file=sys.stderr)

    translation = result.get("full_translation_en", "")
    print(f"[result] full_translation_en: {len(translation)} chars", file=sys.stderr)
    print(f"[result] sections: {len(result.get('sections', []))}", file=sys.stderr)
    print(f"[result] speakers: {len(result.get('all_speakers_mentioned', []))}", file=sys.stderr)
    print(f"[result] agenda_tags: {result.get('agenda_tags', [])}", file=sys.stderr)

    if args.compare:
        existing = read_file(Path(args.compare))
        existing_len = len(existing)
        overlap = len(set(translation.split()) & set(existing.split()))
        total = max(len(set(translation.split())), len(set(existing.split())))
        sim = overlap / total if total > 0 else 0
        print(f"[compare] existing translation: {existing_len} chars", file=sys.stderr)
        print(f"[compare] word overlap ratio: {sim:.2f}", file=sys.stderr)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"[output] saved to {out_path}", file=sys.stderr)
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
