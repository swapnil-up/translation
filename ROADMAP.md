# ROADMAP — Nepali Admin Copilot

## 2026-07 · Current State

| Area | Status |
|------|--------|
| OCR pipeline (PaddleOCR) | Done — rasterizes everything, no pre-processing |
| Gemini freeform translation | Done — block-based, no structured output |
| Notice scraper | Done — `scripts/scrape_notices.py`, current 7th HoR only (~124 entries) |
| Notice processor | Done — `scripts/process_notice.py`, GH Actions cron |
| FastAPI backend | Done — upload → OCR → translate endpoints |
| Vue.js frontend | Basic — upload + overlay/text view, no search |
| Budget PDF extraction (v3) | Working — PyMuPDF + CID fixups for redbook8283.pdf |
| Database | None — all file-based |
| Embeddings / vector search | None |
| Alerts | None |
| Image pre-processing | None — deemed unnecessary for digital PDFs |

---

## Phase 1 — Structured Translation + pgvector

### 1a. Gemini → structured JSON (both outputs from one call)

Modify the translate step to request a JSON response with `response_mime_type="application/json"` and a Pydantic-style schema.

**Output per chunk:**

```json
{
  "full_translation_en": "Full narrative paragraph...",
  "session_date_bs": "2081-04-12",
  "session_date_ad": "2024-07-27",
  "meeting_type": "House of Representatives - Zero Hour",
  "section": "zero_hour",
  "summary_en": "3-bullet summary...",
  "speakers": [
    {"name": "Ramesh Lekhak", "party": "NC", "topic": "Infrastructure delays"}
  ],
  "agenda_tags": ["budget allocation", "fast track project", "infrastructure"],
  "ministries": ["Ministry of Physical Infrastructure"],
  "bill_ids": []
}
```

- **Chunking strategy:** Split on logical boundaries (speaker changes, agenda items) before sending to Gemini. Each chunk gets a structured call.
- **Full translation saved** as `.txt` in `translations/` for human readers (same as now).

### 1b. Embedding pipeline

- Each chunk's `full_translation_en` → prepend contextual header:
  ```
  [Document: {title} | Date: {date_bs} | Section: {section}]
  {chunk_text}
  ```
- Send to `text-embedding-004` → 768-dim vector.
- Same script generates both the embedding and the metadata.

### 1c. Database — Postgres + pgvector (Supabase/Neon from day one)

**Schema:**

```sql
CREATE TABLE notices (
  id UUID PRIMARY KEY,
  file_hash TEXT UNIQUE NOT NULL,
  title TEXT,
  date_bs TEXT,
  date_ad DATE,
  meeting_type TEXT,
  scraped_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE chunks (
  id UUID PRIMARY KEY,
  notice_id UUID REFERENCES notices(id),
  chunk_index INT,
  chunk_text TEXT,
  embedding VECTOR(768),
  -- metadata columns for SQL filtering
  section TEXT,
  speaker_names TEXT[],
  speaker_parties TEXT[],
  agenda_tags TEXT[],
  ministries TEXT[],
  bill_ids TEXT[],
  summary_en TEXT,
  full_translation_en TEXT
);

CREATE INDEX idx_chunks_embedding ON chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
```

- **UPSERT logic:** `ON CONFLICT (file_hash)` to prevent duplicate runs.

### 1d. Script order (modified `process_notice.py`)

```
PDF download → PyMuPDF/PaddleOCR → Gemini structured JSON
  → save full_translation_en.txt to translations/
  → chunk + embed → upsert to pgvector
```

- No SQLite intermediate. First run goes straight to Postgres.
- Gemini quota handling stays the same (retry + backoff).

## Phase 2 — Web App (Vue.js)

- Keep Vue.js (replace SvelteKit idea). Too early to switch; the current app works for testing.
- Add: vector similarity search bar → `SELECT * FROM chunks ORDER BY embedding <=> $1 LIMIT 20`
- Add: split document viewer (English translation + PDF page side-by-side)
- Add: basic analytics (speaker frequency, topic trends over time)

## Phase 3 — Alerts (Telegram/WhatsApp)

- GH Action cron → query recent upserts → format digest from `summary_en` + speakers → push via Telegram Bot API (simplest, no Meta approval).

## Phase 4 — Budget Pipeline Integration (later)

- Connect v3 budget extraction output to the same Postgres schema.
- Cross-reference: "what was allocated" (budget) vs "what was discussed" (notices).

## Non-Goals (for now)

- Image pre-processing (deskew, contrast, cropping) — all inputs are digital PDFs.
- SvelteKit migration.
- WhatsApp Business API (Telegram first, simpler).

## Decisions Log

| Date | Decision |
|------|----------|
| 2026-07 | One Gemini call returns both `full_translation_en` + structured JSON fields |
| 2026-07 | No SQLite intermediate — pgvector from first DB write |
| 2026-07 | Keep always-OCR PDF extraction (no digital vs scanned routing) |
| 2026-07 | Freeform agenda tags from Gemini (no controlled vocabulary yet) |
| 2026-07 | Keep Vue.js frontend (no SvelteKit) |
