import argparse
import os
import re
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import requests
from pdf2image import convert_from_path

# PaddlePaddle 3.3.0+ CPU oneDNN regression workaround (harmless on 3.2.x)
os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")
os.environ.setdefault("FLAGS_allocator_strategy", "naive_best_fit")

from paddleocr import PaddleOCR

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models"

DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


class NepaliOCRProcessor:
    """OCR processor for Nepali Devanagari PDFs.

    Loads PaddleOCR once at init — shared across all requests.
    Use ``ocr_pdf()`` for the web app; the CLI entry point (``main()``)
    wraps the same class.
    """

    def __init__(self):
        self.ocr = PaddleOCR(
            text_recognition_model_name="devanagari_PP-OCRv5_mobile_rec",
            text_detection_model_name="PP-OCRv5_mobile_det",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )

    def ocr_pdf(self, file_path: Optional[str] = None, images: Optional[list] = None, dpi: int = 100) -> dict:
        """Run OCR on a PDF and return structured results.

        Pass either ``file_path`` (converts internally) or ``images`` (pre-converted).

        Returns::

            {
                "full_text": "नेपाल सरकार...",
                "pages": [
                    {
                        "page_number": 1,
                        "text": "...",
                        "words": [
                            {"text": "...", "x": int, "y": int, "width": int, "height": int},
                            ...
                        ]
                    },
                    ...
                ],
                "page_errors": {"3": "image too dark", ...}
            }
        """
        if images is None:
            if file_path is None:
                raise ValueError("Either file_path or images must be provided")
            images = convert_from_path(file_path, dpi=dpi)

        full_lines = []
        pages = []
        page_errors = {}

        for page_idx, img in enumerate(images):
            page_num = page_idx + 1
            page_words = []
            try:
                arr = np.array(img.convert("RGB"))
                result = self.ocr.predict(arr)
                for record in result:
                    texts = record.get("rec_texts", [])
                    scores = record.get("rec_scores", [])
                    boxes = record.get("rec_boxes", [])
                    for i in range(len(texts)):
                        t = texts[i].strip()
                        s = scores[i]
                        if s < 0.3 or not t:
                            continue
                        dev_ratio = len(DEVANAGARI_RE.findall(t)) / max(len(t), 1)
                        if dev_ratio < 0.4 and len(t) >= 2 and s < 0.7:
                            continue
                        b = boxes[i]
                        if hasattr(b, "shape") and len(b.shape) == 1 and b.shape[0] == 4:
                            x1, y1, x2, y2 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
                        else:
                            x1, y1 = int(b[0][0]), int(b[0][1])
                            x2, y2 = int(b[2][0]), int(b[2][1])
                        word = {
                            "text": t,
                            "x": x1,
                            "y": y1,
                            "width": max(x2 - x1, 60),
                            "height": max(y2 - y1, 14),
                        }
                        page_words.append(word)
                        full_lines.append({"y": y1, "x": x1, "w": word["width"], "h": word["height"], "text": t, "page": page_idx})

            except Exception as e:
                page_errors[str(page_num)] = str(e)

            page_text = " ".join(w["text"] for w in page_words)
            pages.append({
                "page_number": page_num,
                "text": page_text,
                "words": page_words,
            })

        full_lines.sort(key=lambda r: (r["page"], r["y"], r["x"]))
        full_text = "\n".join(r["text"] for r in full_lines)

        return {
            "full_text": full_text,
            "pages": pages,
            "page_errors": page_errors,
        }

    def pdf_to_images(self, pdf_path: str, dpi: int = 300) -> list:
        """Convert PDF pages to PIL Images."""
        return convert_from_path(pdf_path, dpi=dpi)


# ── Standalone functions (shared by CLI + HTML overlay) ─────────────────


def group_into_blocks(lines: list, y_gap: int = 20) -> list:
    blocks = []
    cur = [lines[0]]
    for line in lines[1:]:
        same_page = line["page"] == cur[-1]["page"]
        small_gap = line["y"] - (cur[-1]["y"] + cur[-1].get("h", 14)) <= y_gap
        if same_page and small_gap:
            cur.append(line)
        else:
            blocks.append(cur)
            cur = [line]
    if cur:
        blocks.append(cur)
    return blocks


def translate_lines(lines: list, api_key: str) -> list:
    blocks = group_into_blocks(lines)
    print(f"[translate] {len(blocks)} blocks from {len(lines)} lines → {GEMINI_MODEL}", file=sys.stderr, flush=True)

    block_texts = []
    for i, block in enumerate(blocks):
        text = " ".join(r["text"] for r in block)
        block_texts.append(f"=== Block {i}\n{text}")

    prompt = (
        "Translate each Nepali block below to English. "
        "Preserve the === Block N markers exactly on their own line. "
        "Output one translation per block, keeping the marker:\n\n"
        + "\n\n".join(block_texts)
    )

    resp = requests.post(
        f"{GEMINI_API}/{GEMINI_MODEL}:generateContent",
        headers={"Content-Type": "application/json"},
        params={"key": api_key},
        json={
            "system_instruction": {"parts": [{"text": "You are an expert bilingual administrative translator. Output plain English in natural SVO order."}]},
            "contents": [{"parts": [{"text": prompt}]}],
        },
    )
    if not resp.ok:
        err = resp.json().get("error", {}).get("message", resp.text[:200])
        raise RuntimeError(f"Gemini API error: {err}")

    candidates = resp.json().get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError("Gemini returned empty content")

    result = {}
    current_idx = None
    for line in parts[0].get("text", "").split("\n"):
        m = re.match(r"^=== Block (\d+)", line)
        if m:
            current_idx = int(m.group(1))
            result[current_idx] = ""
        elif current_idx is not None and line.strip():
            result[current_idx] = (result[current_idx] + " " + line.strip()).strip()

    for i, block in enumerate(blocks):
        trans = result.get(i, "")
        for entry in block:
            entry["translation"] = trans

    translated = sum(1 for r in lines if r.get("translation"))
    print(f"[translate] Received {translated}/{len(lines)} lines translated", file=sys.stderr, flush=True)
    return lines


def generate_html(lines: list, images: list, out_dir: str, stem: str, night_mode: bool = False) -> str:
    by_page = {}
    for r in lines:
        by_page.setdefault(r["page"], []).append(r)

    def pct(v, total):
        return round(v / total * 100, 4)

    nav_links = ""
    pages_html = ""

    num_pages = len(by_page)
    for page_idx in sorted(by_page):
        print(f"[html]  Page {page_idx + 1}/{num_pages}...", file=sys.stderr, flush=True)
        img = images[page_idx]
        iw, ih = img.size
        img_name = f"{stem}-page-{page_idx + 1}.png"
        img_path = Path(out_dir) / img_name
        if not img_path.exists():
            img.save(str(img_path), format="PNG")

        nav_links += f'<a href="#page-{page_idx + 1}" class="pn">{page_idx + 1}</a>\n'

        cards = ""
        for r in by_page[page_idx]:
            bl = pct(r["x"], iw)
            bt = pct(r["y"], ih)
            bw = pct(r["w"], iw)
            bh = pct(r["h"], ih)

            content = f'<div class="np">{r["text"]}</div>'
            trans = r.get("translation", "")
            if trans:
                content += f'<div class="en">{trans}</div>'
            cards += f'<div class="block" style="left:{bl}%;top:{bt}%;width:{bw}%;height:{bh}%;">{content}</div>\n'

        pages_html += f"""<div class="page" id="page-{page_idx + 1}">
<h2 class="pl">Page {page_idx + 1}</h2>
<img class="bg" src="{img_name}">
{cards}
</div>
"""

    if night_mode:
        extra_style = """body { background: #0a0a0a; }
.bg { filter: brightness(0.2) saturate(0.4) sepia(0.3); }
.block { background: rgba(0,0,0,0.65); overflow: hidden; }
.block:hover { background: rgba(10,10,10,0.95); overflow: visible; height: auto !important; }
.np { color: #e8c44a; }
.en { color: #88ccee; }"""
    else:
        extra_style = """body { background: #1a1a1a; }
.block { background: rgba(0,0,0,0.7); overflow: hidden; }
.block:hover { background: rgba(0,0,0,0.9); overflow: visible; height: auto !important; }
.np { color: #00eeff; }
.en { color: #88ddff; }"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>OCR — {stem}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
nav {{ position: fixed; top: 0; left: 0; right: 0; z-index: 1000; background: rgba(30,30,30,0.95); padding: 8px 16px; text-align: center; }}
.pn {{ display: inline-block; color: #aaa; text-decoration: none; font: 14px/1 sans-serif; padding: 4px 10px; margin: 0 2px; border-radius: 3px; }}
.pn:hover {{ background: #555; color: #fff; }}
body {{ padding: 50px 20px 20px; }}
.page {{ position: relative; width: 100%; max-width: 2550px; margin: 0 auto 40px; scroll-margin-top: 50px; }}
.pl {{ position: absolute; top: -30px; left: 0; font: 13px/1 sans-serif; color: #666; }}
.bg {{ display: block; width: 100%; height: auto; }}
.block {{ position: absolute; font-family: 'Noto Sans', 'Noto Sans Devanagari', sans-serif; white-space: normal; border-radius: 2px; padding: 1px 3px; overflow: hidden; transition: transform 0.15s ease; z-index: 1; word-wrap: break-word; }}
.block:hover {{ z-index: 100; overflow: visible; height: auto !important; transform: none; }}
.block:hover .np {{ font-size: clamp(20px, 1.8vw, 36px); }}
.block:hover .en {{ font-size: clamp(18px, 1.6vw, 32px); }}
.np {{ font-size: clamp(13px, 0.9vw, 20px); }}
.en {{ font-size: clamp(11px, 0.75vw, 17px); }}
{extra_style}
</style>
</head>
<body>
<nav>
{nav_links}
</nav>
{pages_html}
</body>
</html>"""
    return html


def load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


def main():
    load_env()

    parser = argparse.ArgumentParser(description="Extract Devanagari text from Nepali PDF via OCR")
    parser.add_argument("pdf", help="Path to the input PDF file")
    parser.add_argument("--dpi", type=int, default=300, help="DPI for PDF rendering (default: 300)")
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)")
    parser.add_argument("--html", action="store_true", help="Generate positioned HTML overlay")
    parser.add_argument("--night", action="store_true", help="Night mode (dark background, dimmed image, warm text)")
    parser.add_argument(
        "--translate", nargs="?", const="env", metavar="API_KEY",
        help="Translate to English via Gemini. Pass API key, or omit to use GEMINI_API_KEY env var",
    )
    args = parser.parse_args()

    pdf = Path(args.pdf)
    if not pdf.exists():
        print(f"Error: {pdf} not found", file=sys.stderr)
        sys.exit(1)

    processor = NepaliOCRProcessor()

    print(f"[stage] 1/4 — Rasterise PDF", file=sys.stderr, flush=True)
    images = processor.pdf_to_images(str(pdf), dpi=args.dpi)
    print(f"[stage] 2/4 — OCR {len(images)} page(s)", file=sys.stderr, flush=True)
    result = processor.ocr_pdf(str(pdf), dpi=args.dpi)
    lines = []
    for p in result["pages"]:
        for w in p["words"]:
            lines.append({"y": w["y"], "x": w["x"], "w": w["width"], "h": w["height"], "text": w["text"], "page": p["page_number"] - 1})

    if args.translate:
        print(f"[stage] 3/4 — Translate to English", file=sys.stderr, flush=True)
        api_key = os.environ.get("GEMINI_API_KEY") if args.translate == "env" else args.translate
        if not api_key:
            print("Error: GEMINI_API_KEY not set. Add to .env, pass --translate=KEY, or export GEMINI_API_KEY", file=sys.stderr)
            sys.exit(1)
        lines = translate_lines(lines, api_key)
    else:
        print(f"[stage] 3/4 — (skipped, no --translate)", file=sys.stderr, flush=True)

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)

    if args.html:
        print(f"[stage] 4/4 — Generate HTML overlay", file=sys.stderr, flush=True)
        stem = Path(args.output).stem if args.output else pdf.stem
        html_path = str(out_dir / f"{stem}.html")
        if args.output:
            html_path = args.output

        html = generate_html(lines, images, str(out_dir), stem, night_mode=args.night)
        Path(html_path).write_text(html, encoding="utf-8")
        print(f"Written to {html_path}")

        if args.translate:
            txt_path = out_dir / f"{stem}-translated.txt"
            txt_path.write_text(
                "\n".join(r.get("translation", "") for r in lines),
                encoding="utf-8"
            )
            print(f"Written to {txt_path}")

        txt_path = out_dir / f"{stem}-ocr.txt"
        txt_path.write_text(
            "\n".join(r["text"] for r in lines),
            encoding="utf-8"
        )
        print(f"Written to {txt_path}")
    else:
        text = "\n".join(r.get("translation", r["text"]) for r in lines)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
            print(f"Written to {args.output}")
        else:
            print(text)


if __name__ == "__main__":
    main()
