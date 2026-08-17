import os
import sys

os.environ["PADDLEX_HOME"] = "/root/.paddlex"
os.environ["XDG_CACHE_HOME"] = "/root/.cache"
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
os.environ["FLAGS_allocator_strategy"] = "naive_best_fit"

print("Pre-downloading PaddleOCR Devanagari models...")
sys.stdout.flush()

try:
    from paddleocr import PaddleOCR  # noqa: E402

    PaddleOCR(
        text_recognition_model_name="devanagari_PP-OCRv5_mobile_rec",
        text_detection_model_name="PP-OCRv5_mobile_det",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    print("Models successfully baked into the cache!")
except Exception as e:
    print(f"Model pre-download failed (will download at runtime): {e}", file=sys.stderr)
    sys.stdout.flush()
