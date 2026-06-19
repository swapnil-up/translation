import requests

from app.config import settings

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models"


def translate_devanagari_to_english(text: str) -> str:
    if not settings.gemini_api_key:
        raise ValueError("Gemini API key not configured")

    prompt = (
        "Translate the following Nepali government document text to English. "
        "Preserve all numbers, amounts, and codes exactly as-is. "
        "Output clean English in natural SVO order.\n\n"
        f"{text}"
    )

    resp = requests.post(
        f"{GEMINI_API}/{GEMINI_MODEL}:generateContent",
        headers={"Content-Type": "application/json"},
        params={"key": settings.gemini_api_key},
        json={
            "system_instruction": {
                "parts": [{"text": "You are an expert bilingual administrative translator. Output plain English only."}]
            },
            "contents": [{"parts": [{"text": prompt}]}],
        },
    )

    if not resp.ok:
        err = resp.json().get("error", {}).get("message", resp.text[:300])
        raise RuntimeError(f"Gemini API error: {err}")

    candidates = resp.json().get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError("Gemini returned empty content")

    return parts[0].get("text", "").strip()
