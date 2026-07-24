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


def is_quota_error(stderr: str) -> bool:
    return any(p in stderr for p in ["429", "403", "RESOURCE_EXHAUSTED", "quota", "rate limit"])


def run_ocr(pdf_path: Path) -> dict:
    stem = pdf_path.stem
    out_txt = TRANSLATIONS_DIR / f"{stem}.txt"
    ocr_txt = TRANSLATIONS_DIR / f"{stem}-ocr.txt"
    api_key = os.environ.get("GEMINI_API_KEY", "")

    cmd = [
        sys.executable, "pdf_to_text.py",
        str(pdf_path),
        "-o", str(out_txt),
    ]
    if api_key:
        cmd.extend(["--translate", api_key])
        print(f"[ocr] OCR + translate -> {ocr_txt}, {out_txt}")
    else:
        print(f"[ocr] OCR only -> {out_txt}")

    TRANSLATIONS_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr + result.stdout
        if is_quota_error(err):
            raise RuntimeError("QUOTA_EXHAUSTED: " + err[-500:])
        raise RuntimeError(err[-500:])

    result_dict = {"ocr_path": str(ocr_txt if ocr_txt.exists() else out_txt)}
    if api_key and out_txt.exists():
        result_dict["translated_path"] = str(out_txt)
    return result_dict


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

    try:
        result = run_ocr(pdf_dest)
        notices[index].update(result)
        notices[index]["status"] = "done"
        save_manifest(notices)
        print(f"[done] {notice['title']}")
        return True
    except RuntimeError as e:
        msg = str(e)
        if "QUOTA_EXHAUSTED" in msg:
            print(f"[quota] Gemini credits exhausted — keeping '{notice['title']}' as pending", file=sys.stderr)
            save_manifest(notices)
            return False
        print(f"[error] processing: {msg}", file=sys.stderr)
        notices[index]["status"] = "failed"
        save_manifest(notices)
        return False


def main():
    load_env()
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[warn] GEMINI_API_KEY not set — OCR only, no translation", file=sys.stderr)

    notices = load_manifest()
    if not notices:
        print("[error] notices.json empty — run scrape first", file=sys.stderr)
        return

    idx = pick_pending(notices)
    if idx is None:
        print("[done] no pending notices")
        return

    process_one(notices[idx], idx, notices)


if __name__ == "__main__":
    main()