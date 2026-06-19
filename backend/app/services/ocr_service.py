import asyncio
import os
import shutil
import uuid
from typing import Optional

from app.schemas import OcrTaskState

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

            # --- OCR logic will go here (Phase 1a/1c) ---
            # from pdf_to_text import NepaliOCRProcessor
            # processor = NepaliOCRProcessor()
            # result = processor.ocr_pdf(file_path)

            # Stub:
            await asyncio.sleep(0.1)
            result = {
                "full_text": "OCR result placeholder",
                "pages": []
            }

            # Clean up source PDF
            if os.path.isfile(file_path):
                os.remove(file_path)

            tasks_db[task_id].status = "done"
            tasks_db[task_id].phase = "completed"
            tasks_db[task_id].result = result["full_text"]

        except Exception as e:
            tasks_db[task_id].status = "error"
            tasks_db[task_id].phase = "failed"
            tasks_db[task_id].error = str(e)
