import os

os.environ["PADDLEX_HOME"] = "/root/.paddlex"
os.environ["XDG_CACHE_HOME"] = "/root/.cache"

print("Pre-downloading PaddleOCR Devanagari/Hindi models...")

from paddleocr import PaddleOCR  # noqa: E402

PaddleOCR(lang="hi", use_textline_orientation=True)

print("Models successfully baked into the cache!")
