# === Stage 1: Build Vue Frontend ===
FROM node:20-slim AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# === Stage 2: Final Python Runtime ===
FROM python:3.10-slim
WORKDIR /code

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0t64 \
    libgomp1 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

ENV PADDLEX_HOME=/root/.paddlex \
    XDG_CACHE_HOME=/root/.cache \
    PYTHONUNBUFFERED=1 \
    PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=0 \
    FLAGS_allocator_strategy=naive_best_fit \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_NO_CACHE_DIR=1

COPY backend/requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --prefer-binary -r requirements.txt

COPY backend/ ./
RUN python download_models.py

COPY --from=frontend-builder /build/dist ./static_dist

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/api/config/status')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
