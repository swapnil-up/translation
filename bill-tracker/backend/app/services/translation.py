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


ContextItem = tuple[list[str], int]  # (all lines in block, target line index)


def translate_blocks(
    blocks_by_key: dict[str, str],
    context: dict[str, ContextItem] | None = None,
) -> dict[str, str]:
    """Translate multiple text items in a single Gemini call.

    Each item (key → text) is sent with a sequential marker, and the
    response is parsed back into the same keys.  Works for both block-level
    and line-level keys.

    When *context* is provided, each item's surrounding lines are included
    so Gemini can translate the target line more accurately.  Each context
    value is (list_of_all_block_lines, target_line_index).

    Returns:
        Same keys mapped to English translations.
    """
    if not settings.gemini_api_key:
        raise ValueError("Gemini API key not configured")

    sorted_keys = list(blocks_by_key.keys())

    input_lines = []
    for i, key in enumerate(sorted_keys):
        text = blocks_by_key[key]
        ctx = (context or {}).get(key)
        if ctx is not None:
            block_lines, target_idx = ctx
            marked = list(block_lines)
            marked[target_idx] = f">>> {marked[target_idx]} <<<"
            input_lines.append(f"--- ITEM {i}\n" + "\n".join(marked))
        else:
            input_lines.append(f"--- ITEM {i}\n{text}")

    prompt = (
        "Translate each Nepali item below to English. "
        "Lines between >>> and <<< are the ones to translate; "
        "surrounding lines are context only. "
        "Output exactly one --- TRANS N section per input item, in order. "
        "Never skip an item. Do not add any introductory text.\n\n"
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
