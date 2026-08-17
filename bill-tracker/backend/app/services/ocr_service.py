import asyncio
import json
import os
import shutil
import uuid
from typing import Optional

from pdf2image import convert_from_path

from app.schemas import OcrTaskState, OcrPage, OcrWord, OcrLine, OcrBlock

tasks_db: dict[str, OcrTaskState] = {}
ocr_lock = asyncio.Lock()
UPLOAD_BASE = "/tmp/uploads"
STATE_FILE = "state.json"


def save_task_state(task_id: str):
    task = tasks_db.get(task_id)
    if not task:
        return
    task_dir = os.path.join(UPLOAD_BASE, task_id)
    os.makedirs(task_dir, exist_ok=True)
    path = os.path.join(task_dir, STATE_FILE)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(task.model_dump(mode="json"), f, ensure_ascii=False)
    except Exception:
        pass


def load_task_state(task_id: str) -> Optional[OcrTaskState]:
    path = os.path.join(UPLOAD_BASE, task_id, STATE_FILE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return OcrTaskState.model_validate(data)
    except Exception:
        return None


def get_task(task_id: str) -> Optional[OcrTaskState]:
    task = tasks_db.get(task_id)
    if task:
        return task
    return load_task_state(task_id)

Y_TOLERANCE = 8


def group_words_into_lines(words: list[OcrWord]) -> list[OcrLine]:
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w.y, w.x))
    lines = []
    current_line = [sorted_words[0]]
    for w in sorted_words[1:]:
        last = current_line[-1]
        if abs(w.y - last.y) <= Y_TOLERANCE:
            current_line.append(w)
        else:
            joined = " ".join(wrd.text for wrd in current_line)
            min_x = min(wrd.x for wrd in current_line)
            min_y = min(wrd.y for wrd in current_line)
            max_x = max(wrd.x + wrd.width for wrd in current_line)
            max_y = max(wrd.y + wrd.height for wrd in current_line)
            lines.append(OcrLine(text=joined, x=min_x, y=min_y, width=max_x - min_x, height=max_y - min_y))
            current_line = [w]
    if current_line:
        joined = " ".join(wrd.text for wrd in current_line)
        min_x = min(wrd.x for wrd in current_line)
        min_y = min(wrd.y for wrd in current_line)
        max_x = max(wrd.x + wrd.width for wrd in current_line)
        max_y = max(wrd.y + wrd.height for wrd in current_line)
        lines.append(OcrLine(text=joined, x=min_x, y=min_y, width=max_x - min_x, height=max_y - min_y))
    return lines


def group_lines_into_blocks(lines: list[OcrLine], y_gap: int = 20) -> list[OcrBlock]:
    if not lines:
        return []
    blocks = []
    current = [lines[0]]
    for line in lines[1:]:
        last = current[-1]
        gap = line.y - (last.y + last.height)
        if gap <= y_gap:
            current.append(line)
        else:
            min_x = min(l.x for l in current)
            min_y = min(l.y for l in current)
            max_x = max(l.x + l.width for l in current)
            max_y = max(l.y + l.height for l in current)
            blocks.append(OcrBlock(lines=list(current), x=min_x, y=min_y, width=max_x - min_x, height=max_y - min_y))
            current = [line]
    if current:
        min_x = min(l.x for l in current)
        min_y = min(l.y for l in current)
        max_x = max(l.x + l.width for l in current)
        max_y = max(l.y + l.height for l in current)
        blocks.append(OcrBlock(lines=list(current), x=min_x, y=min_y, width=max_x - min_x, height=max_y - min_y))
    return blocks


def get_queue_position(task_id: str) -> int:
    position = 1
    for tid, task in tasks_db.items():
        if tid == task_id:
            return position
        if task.status in ("pending", "processing"):
            position += 1
    return position


async def cleanup_task_resources(task_id: str, delay_seconds: int = 7200):
    await asyncio.sleep(delay_seconds)
    tasks_db.pop(task_id, None)
    task_dir = os.path.join(UPLOAD_BASE, task_id)
    if os.path.isdir(task_dir):
        try:
            shutil.rmtree(task_dir)
        except Exception:
            pass


async def run_ocr_pipeline_task(task_id: str, file_path: str):
    tasks_db[task_id] = OcrTaskState(
        status="pending", phase="queued",
        current=0, total=0
    )
    async with ocr_lock:
        try:
            tasks_db[task_id].status = "processing"
            tasks_db[task_id].phase = "converting_pdf"

            # Convert to images and save page JPEGs for overlay
            images = convert_from_path(file_path, dpi=100)
            pages_dir = os.path.join(UPLOAD_BASE, task_id, "pages")
            os.makedirs(pages_dir, exist_ok=True)
            for i, img in enumerate(images, start=1):
                img.save(os.path.join(pages_dir, f"{i}.jpg"), format="JPEG", quality=80)
            tasks_db[task_id].total = len(images)

            # Clean up source PDF
            if os.path.isfile(file_path):
                os.remove(file_path)

            # Run OCR
            tasks_db[task_id].phase = "ocr"

            from pdf_to_text import NepaliOCRProcessor
            processor = NepaliOCRProcessor()
            result = processor.ocr_pdf(images=images)

            pages = []
            for p in result["pages"]:
                words = [OcrWord(**w) for w in p["words"]]
                page_status = "failed" if p["page_number"] in result.get("page_errors", {}) else ("blank" if not words else "success")
                lines_list = group_words_into_lines(words) if words else []
                blocks_list = group_lines_into_blocks(lines_list) if lines_list else []
                pages.append(OcrPage(
                    page_number=p["page_number"],
                    text=p["text"],
                    words=words,
                    lines=lines_list,
                    blocks=blocks_list,
                    status=page_status,
                ))

            page_errors_converted = {int(k): v for k, v in result.get("page_errors", {}).items()}
            successful_pages = len([p for p in pages if p.status == "success"])

            tasks_db[task_id].current = successful_pages
            tasks_db[task_id].pages = pages
            tasks_db[task_id].page_errors = page_errors_converted

            tasks_db[task_id].status = "done"
            tasks_db[task_id].phase = "completed"
            tasks_db[task_id].result = result["full_text"]

            save_task_state(task_id)

        except Exception as e:
            tasks_db[task_id].status = "error"
            tasks_db[task_id].phase = "failed"
            tasks_db[task_id].error = str(e)
            save_task_state(task_id)
