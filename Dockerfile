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

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libgl1 \
    libglib2.0-0t64 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PADDLEX_HOME=/root/.paddlex
ENV XDG_CACHE_HOME=/root/.cache
ENV PYTHONUNBUFFERED=1

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
RUN python download_models.py

COPY --from=frontend-builder /build/dist ./static_dist

EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
