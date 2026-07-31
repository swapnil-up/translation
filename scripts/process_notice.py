import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib3
from pathlib import Path

import requests
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MANIFEST = Path("notices.json")
TRANSLATIONS_DIR = Path("translations")
OUTPUT_DIR = Path("output")
BASE = "https://hr.parliament.gov.np"
HEADERS = {"User-Agent": "Mozilla/5.0"}

MAX_RETRIES = 3
RETRY_DELAY = 5

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models"

STRUCTURED_SCHEMA_DESC = """
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


def load_manifest() -> list:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return []


def save_manifest(notices: list):
    MANIFEST.write_text(json.dumps(notices, indent=2, ensure_ascii=False))
    print(f"[manifest] saved {len(notices)} entries", file=sys.stderr)


def load_env():
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


def pick_pending(notices: list) -> int | None:
    for i, n in enumerate(notices):
        title = n.get("title", "")
        if title in ("", "(no title)"):
            continue
        if n.get("status") != "pending":
            continue
        pdf = n.get("pdf_url", "")
        if pdf and not pdf.endswith(".pdf"):
            continue
        return i
    return None


def fetch_with_retry(url: str, **kwargs) -> requests.Response | None:
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30, verify=False, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            last_err = e
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY * (2 ** attempt)
                print(f"[retry] {url} ({e}), waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
    print(f"[error] {url}: {last_err}", file=sys.stderr)
    return None


def fetch_page(url: str) -> BeautifulSoup | None:
    resp = fetch_with_retry(url)
    if resp:
        return BeautifulSoup(resp.text, "lxml")
    return None


def backfill_pdf_url(notice: dict) -> str | None:
    url = notice.get("url")
    if not url:
        return None
    soup = fetch_page(url)
    if not soup:
        return None
    for a in soup.select("a[href]"):
        href = a["href"]
        if "/uploads/attachments/" in href:
            if not href.startswith("http"):
                href = BASE + href
            return href
    for a in soup.select("a[href$='.pdf']"):
        href = a["href"]
        if not href.startswith("http"):
            href = BASE + href
        return href
    return None


def download_pdf(pdf_url: str, dest: Path) -> bool:
    print(f"[download] {pdf_url}")
    try:
        resp = fetch_with_retry(pdf_url)
        if not resp:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        print(f"[download] saved {len(resp.content)} bytes to {dest}")
        return True
    except Exception as e:
        print(f"[error] download: {e}", file=sys.stderr)
        return False


def dedup_lines(text: str) -> str:
    lines = text.splitlines()
    result = [lines[0]] if lines else []
    for i in range(1, len(lines)):
        if lines[i] != lines[i - 1]:
            result.append(lines[i])
    return "\n".join(result)


def _classify_gemini_error(err: str) -> str:
    lowered = err.lower()
    if any(p in lowered for p in ["rate limit", "high demand", "try again later"]):
        return "rpm"
    if any(p in err for p in ["429", "403", "RESOURCE_EXHAUSTED", "quota"]):
        return "rpd"
    return "other"


def _output_token_budget(ocr_text: str) -> int:
    chars = len(ocr_text)
    return max(8192, min(chars // 2, 65536))


def run_ocr(pdf_path: Path) -> dict:
    stem = pdf_path.stem
    ocr_txt = TRANSLATIONS_DIR / f"{stem}-ocr.txt"
    api_key = os.environ.get("GEMINI_API_KEY", "")

    cmd = [
        sys.executable, "pdf_to_text.py",
        str(pdf_path),
        "-o", str(ocr_txt),
    ]
    print(f"[ocr] OCR only -> {ocr_txt}")

    TRANSLATIONS_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = (result.stderr or "") + (result.stdout or "")
        raise RuntimeError(err[-500:])

    if ocr_txt.exists():
        ocr_txt.write_text(dedup_lines(ocr_txt.read_text()), encoding="utf-8")

    result_dict = {"ocr_path": str(ocr_txt)}

    if api_key:
        print(f"[translate] structured Gemini extraction...", file=sys.stderr)
        ocr_text = ocr_txt.read_text(encoding="utf-8")
        structured = call_gemini_structured(ocr_text, api_key)

        translation = structured.get("full_translation_en", "")
        out_txt = TRANSLATIONS_DIR / f"{stem}.txt"
        out_txt.write_text(translation, encoding="utf-8")
        print(f"[translate] full translation -> {out_txt} ({len(translation)} chars)", file=sys.stderr)
        result_dict["translated_path"] = str(out_txt)

        out_json = TRANSLATIONS_DIR / f"{stem}.json"
        out_json.write_text(json.dumps(structured, indent=2, ensure_ascii=False))
        print(f"[translate] structured JSON -> {out_json}", file=sys.stderr)
        result_dict["structured_path"] = str(out_json)

    return result_dict


def call_gemini_structured(ocr_text: str, api_key: str) -> dict:
    prompt = STRUCTURED_PROMPT.format(schema=STRUCTURED_SCHEMA_DESC, ocr_text=ocr_text)

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
                "maxOutputTokens": _output_token_budget(ocr_text),
            },
        },
    )

    try:
        body = resp.json()
    except ValueError:
        body = {}

    if not resp.ok:
        err = body.get("error", {}).get("message", resp.text[:500])
        kind = _classify_gemini_error(err)
        if kind in ("rpm", "rpd"):
            raise RuntimeError(f"{kind.upper()}: {err}")
        raise RuntimeError(f"Gemini API error: {err}")

    candidates = body.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")

    candidate = candidates[0]
    finish_reason = candidate.get("finishReason", "")
    parts = candidate.get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError("Gemini returned empty content")

    text = parts[0].get("text", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        if finish_reason == "MAX_TOKENS":
            raise RuntimeError(f"TRUNCATED: Gemini response cut off mid-JSON ({e})")
        raise RuntimeError(f"Gemini returned invalid JSON ({e})")


def process_one(notice: dict, index: int, notices: list) -> bool:
    title_slug = (notice.get("title") or "untitled").replace(" ", "_").replace("/", "_")[:80]
    if not title_slug:
        title_slug = f"notice_{index}"

    pdf_url = notice.get("pdf_url")
    if not pdf_url:
        print(f"[backfill] fetching PDF URL...", file=sys.stderr)
        pdf_url = backfill_pdf_url(notice)
        if pdf_url:
            notices[index]["pdf_url"] = pdf_url
            save_manifest(notices)
        else:
            print(f"[error] no PDF found", file=sys.stderr)
            notices[index]["status"] = "no_pdf"
            save_manifest(notices)
            return False

    pdf_dest = OUTPUT_DIR / f"{title_slug}.pdf"

    if not download_pdf(pdf_url, pdf_dest):
        notices[index]["status"] = "failed"
        save_manifest(notices)
        return False

    max_rpm_retries = 5
    for attempt in range(max_rpm_retries + 1):
        try:
            result = run_ocr(pdf_dest)
            notices[index].update(result)
            notices[index]["status"] = "done"
            save_manifest(notices)
            print(f"[done] {notice['title']}")
            return True
        except RuntimeError as e:
            msg = str(e)
            if msg.startswith(("RPM", "TRUNCATED")):
                if attempt < max_rpm_retries:
                    wait = min(2 ** (attempt + 2), 60)
                    print(f"[retry] {msg.split(':')[0].lower()}, retry {attempt + 1}/{max_rpm_retries} in {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                print(f"[retry] max retries exceeded — keeping '{notice['title']}' as pending", file=sys.stderr)
                save_manifest(notices)
                return False
            if msg.startswith("RPD"):
                print(f"[quota] daily Gemini quota exhausted — keeping '{notice['title']}' as pending", file=sys.stderr)
                save_manifest(notices)
                return False
            print(f"[error] processing: {msg}", file=sys.stderr)
            notices[index]["status"] = "failed"
            save_manifest(notices)
            return False
        except Exception as e:
            print(f"[error] processing: unexpected {type(e).__name__}: {e}", file=sys.stderr)
            notices[index]["status"] = "failed"
            save_manifest(notices)
            return False


def main():
    load_env()

    parser = argparse.ArgumentParser(description="Process pending notices through OCR + Gemini translation")
    parser.add_argument("--max-count", "-n", type=int, default=0,
                        help="Max notices to process per run (0 = unlimited)")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[warn] GEMINI_API_KEY not set — OCR only, no translation", file=sys.stderr)

    notices = load_manifest()
    if not notices:
        print("[error] notices.json empty — run scrape first", file=sys.stderr)
        return

    processed = 0
    max_count = args.max_count

    while True:
        if max_count and processed >= max_count:
            print(f"[limit] reached max-count ({max_count})", file=sys.stderr)
            break

        idx = pick_pending(notices)
        if idx is None:
            print("[done] no pending notices")
            break

        ok = process_one(notices[idx], idx, notices)
        processed += 1

        if not ok and notices[idx].get("status") == "pending":
            print(f"[quota] stopping — {processed} notice(s) processed this run", file=sys.stderr)
            break


if __name__ == "__main__":
    main()