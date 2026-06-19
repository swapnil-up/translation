import re

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


def translate_blocks(blocks_by_key: dict[str, str]) -> dict[str, str]:
    """Translate multiple text blocks in a single Gemini call.

    Uses an enumerated list format with explicit ``--- BLOCK N`` / ``--- TRANS N``
    markers that Gemini is unlikely to strip.

    Returns:
        Same keys mapped to English translations.
    """
    if not settings.gemini_api_key:
        raise ValueError("Gemini API key not configured")

    sorted_keys = list(blocks_by_key.keys())

    input_lines = []
    for i, key in enumerate(sorted_keys):
        text = blocks_by_key[key]
        input_lines.append(f"--- BLOCK {i}\n{text}")

    prompt = (
        "Translate each Nepali block to English. "
        "Output exactly one --- TRANS N section per input block, in order. "
        "Never skip a block. Do not add any introductory text.\n\n"
        + "\n\n".join(input_lines)
    )

    resp = requests.post(
        f"{GEMINI_API}/{GEMINI_MODEL}:generateContent",
        headers={"Content-Type": "application/json"},
        params={"key": settings.gemini_api_key},
        json={
            "system_instruction": {
                "parts": [{"text": "You are an expert bilingual administrative translator. Output plain English in natural SVO order. Always use the --- TRANS N markers."}]
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

    text = parts[0].get("text", "").strip()
    results: dict[str, str] = {}
    block_index = -1
    for line in text.split("\n"):
        if re.match(r"^--- TRANS", line):
            block_index += 1
            if block_index < len(sorted_keys):
                results[sorted_keys[block_index]] = ""
        elif block_index >= 0 and block_index < len(sorted_keys) and line.strip():
            key = sorted_keys[block_index]
            results[key] = (results.get(key, "") + " " + line.strip()).strip()

    for key in sorted_keys:
        results.setdefault(key, "")

    return results
