---
title: Nepali Admin Copilot
emoji: 📄
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
startup_duration_timeout: 1h
---

# Nepali Admin Copilot — Hugging Face Spaces

Deploy this FastAPI + Vue app to extract Devanagari text from Nepali government PDFs.

## One-click setup

1. **Create a Space** at https://huggingface.co/spaces
   - SDK: **Docker**
   - Hardware: **CPU basic** (free)

2. **Push the repo**:
   ```bash
   git remote add space https://huggingface.co/spaces/<your-username>/<space-name>
   git push space main
   ```

3. **Add secrets** (optional, for translation):
   - `GEMINI_API_KEY` — your Google Gemini API key

   Go to your Space → **Settings → Repository Secrets → New secret**.

4. **Wait for the build** (~8–15 min). Watch logs in the **Builder** tab.

## Build notes

| Concern | Status |
|---------|--------|
| Build timeout | Set to 1h in YAML header above |
| PaddlePaddle install | `--prefer-binary` avoids compilation; `PIP_DEFAULT_TIMEOUT=300` prevents dropouts |
| Model weights | Pre-downloaded during build; falls back to runtime download on failure |
| Port | Configured to 7860 (HF default) |
| CPU-only OCR | ~2–5 sec/page; async task polling handles long runs |
| Idle sleep | After 48h; first request cold-start loads PaddleOCR (~10–20s) |

## Usage

Upload a PDF → OCR runs asynchronously → view Devanagari text or translate to English.

- **API**: `POST /api/ocr` upload, `GET /api/ocr/{task_id}` poll
- **Frontend**: SPA served at `https://<your-username>-<space-name>.hf.space/`

## Files for HF Spaces

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build (Node frontend + Python runtime) |
| `README.hf.md` | This file — rename to `README.md` (or merge into yours) |
| `backend/` | FastAPI app + PaddleOCR service |
| `frontend/` | Vue 3 SPA |
