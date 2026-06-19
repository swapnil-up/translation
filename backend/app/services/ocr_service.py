import asyncio
import os
import shutil
import uuid
from typing import Optional

from pdf2image import convert_from_path

from app.schemas import OcrTaskState, OcrPage, OcrWord

tasks_db: dict[str, OcrTaskState] = {}
ocr_lock = asyncio.Lock()
UPLOAD_BASE = "/tmp/uploads"


def get_queue_position(task_id: str) -> int:
    position = 1
    for tid, task in tasks_db.items():
        if tid == task_id:
            return position
        if task.status in ("pending", "processing"):
            position += 1
    return position


async def cleanup_task_resources(task_id: str, delay_seconds: int = 1800):
    await asyncio.sleep(delay_seconds)
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
                pages.append(OcrPage(
                    page_number=p["page_number"],
                    text=p["text"],
                    words=words,
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

        except Exception as e:
            tasks_db[task_id].status = "error"
            tasks_db[task_id].phase = "failed"
            tasks_db[task_id].error = str(e)
