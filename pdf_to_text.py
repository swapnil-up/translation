import argparse
import os
import re
import sys
from pathlib import Path

import numpy as np
import requests
from pdf2image import convert_from_path
from paddleocr import PaddleOCR

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models"

DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def pdf_to_images(pdf_path: str, dpi: int = 300) -> list:
    return convert_from_path(pdf_path, dpi=dpi)


def is_devanagari_line(text: str, min_ratio: float = 0.4) -> bool:
    if not text.strip():
        return False
    dev_len = len(DEVANAGARI_RE.findall(text))
    return dev_len / len(text.strip()) >= min_ratio


def extract_lines(images: list) -> list:
    ocr = PaddleOCR(
        text_recognition_model_name="devanagari_PP-OCRv5_mobile_rec",
        text_detection_model_name="PP-OCRv5_mobile_det",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    lines = []
    for img in images:
        arr = np.array(img)
        result = ocr.predict(arr)
        for record in result:
            texts = record["rec_texts"]
            scores = record["rec_scores"]
            boxes = record["rec_boxes"]
            for i in range(len(texts)):
                t = texts[i].strip()
                s = scores[i]
                if s < 0.3 or not t:
                    continue
                dev_ratio = len(DEVANAGARI_RE.findall(t)) / max(len(t), 1)
                if dev_ratio < 0.4 and len(t) >= 2 and s < 0.7:
                    continue
                x1, y1, x2, y2 = [int(boxes[i][j]) for j in range(4)]
                lines.append({"y": y1, "x": x1, "w": max(x2 - x1, 60), "h": max(y2 - y1, 14), "text": t})
    lines.sort(key=lambda r: (r["y"], r["x"]))
    return lines


def lines_to_plain(lines: list) -> str:
    return "\n".join(r["text"] for r in lines)


def translate_lines(lines: list, api_key: str) -> list:
    tagged = "\n".join(f"[{i}] {r['text']}" for i, r in enumerate(lines))

    system_instruction = (
        "You are an expert bilingual administrative translator. "
        "Translate Nepali government notices into plain, professional English. "
        "Fix grammar to English Subject-Verb-Object order. "
        "CRITICAL: preserve the [index] markers exactly — output each translated line "
        "on the same [index] as its Nepali source, one per line."
    )

    resp = requests.post(
        f"{GEMINI_API}/{GEMINI_MODEL}:generateContent",
        headers={"Content-Type": "application/json"},
        params={"key": api_key},
        json={
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [
                {
                    "parts": [{
                        "text": (
                            "Translate each tagged line. Keep every [index] marker in the output "
                            "with its corresponding translation on the same line:\n\n"
                            f"{tagged}"
                        )
                    }]
                }
            ],
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
    for line in parts[0].get("text", "").split("\n"):
        m = re.match(r"^\[(\d+)\]\s*(.*)", line)
        if m:
            result[int(m.group(1))] = m.group(2).strip()

    for i, entry in enumerate(lines):
        entry["translation"] = result.get(i, "")
    return lines


def generate_html(lines: list, pdf_path: str, image_path: str, dpi: int) -> str:
    img = convert_from_path(pdf_path, dpi=dpi)[0]
    iw, ih = img.size

    if not Path(image_path).exists():
        img.save(image_path, format="PNG")

    def pct(v, total):
        return round(v / total * 100, 4)

    cards = ""
    for r in lines:
        nep = r["text"]
        eng = r.get("translation", "")
        l = pct(r["x"], iw)
        t = pct(r["y"], ih)
        w = pct(r["w"], iw)
        style = f"left:{l}%;top:{t}%;width:{w}%;"
        cards += f'<div class="box" style="{style}"><div class="np">{nep}</div>'
        if eng:
            cards += f'<div class="en">{eng}</div>'
        cards += "</div>\n"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>OCR Output — {Path(pdf_path).name}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #1a1a1a; display: flex; justify-content: center; padding: 20px; }}
.container {{ position: relative; width: 100%; max-width: 2550px; }}
.bg {{ display: block; width: 100%; height: auto; }}
.box {{ position: absolute; font-family: 'Noto Sans', 'Noto Sans Devanagari', sans-serif; white-space: nowrap; background: rgba(0,0,0,0.55); border-radius: 2px; padding: 0 2px; transition: transform 0.15s ease; z-index: 1; }}
.box:hover {{ transform: none; z-index: 100; background: rgba(0,0,0,0.9); white-space: normal; min-width: 30vw; max-width: 60vw; }}
.box:hover .np {{ font-size: clamp(20px, 1.8vw, 36px); }}
.box:hover .en {{ font-size: clamp(18px, 1.6vw, 32px); }}
.np {{ color: #00ccff; font-size: clamp(13px, 0.9vw, 20px); }}
.en {{ color: #ffcc00; font-size: clamp(11px, 0.75vw, 17px); }}
</style>
</head>
<body>
<div class="container">
<img class="bg" src="{Path(image_path).name}">
{cards}
</div>
</body>
</html>"""
    return html


def load_env():
    env_path = Path(".env")
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
    parser.add_argument(
        "--translate", nargs="?", const="env", metavar="API_KEY",
        help="Translate to English via Gemini. Pass API key, or omit to use GEMINI_API_KEY env var",
    )
    args = parser.parse_args()

    pdf = Path(args.pdf)
    if not pdf.exists():
        print(f"Error: {pdf} not found", file=sys.stderr)
        sys.exit(1)

    images = pdf_to_images(str(pdf), dpi=args.dpi)
    lines = extract_lines(images)

    if args.translate:
        api_key = os.environ.get("GEMINI_API_KEY") if args.translate == "env" else args.translate
        if not api_key:
            print("Error: GEMINI_API_KEY not set. Add to .env, pass --translate=KEY, or export GEMINI_API_KEY", file=sys.stderr)
            sys.exit(1)
        lines = translate_lines(lines, api_key)

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)

    if args.html:
        stem = Path(args.output).stem if args.output else pdf.stem
        img_path = str(out_dir / f"{stem}.png")
        html_path = str(out_dir / f"{stem}.html")
        if args.output:
            html_path = args.output

        html = generate_html(lines, str(pdf), img_path, args.dpi)
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
        txt_path.write_text(lines_to_plain(lines), encoding="utf-8")
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
