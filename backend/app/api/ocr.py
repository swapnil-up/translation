import asyncio
import os
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse

from app.config import settings
from app.schemas import OcrResult
from app.services.ocr_service import (
    get_task,
    ocr_lock,
    run_ocr_pipeline_task,
    cleanup_task_resources,
    save_task_state,
    UPLOAD_BASE,
)
from app.services.translation import translate_devanagari_to_english, translate_blocks

router = APIRouter()
TRANSLATION_BATCH_SIZE = 10


@router.post("/ocr")
async def start_ocr(file: UploadFile = File(...)):
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Upload exceeds {settings.max_upload_size_mb}MB limit",
        )

    task_id = str(uuid.uuid4())
    task_dir = os.path.join(UPLOAD_BASE, task_id)
    os.makedirs(task_dir, exist_ok=True)
    file_path = os.path.join(task_dir, "source.pdf")
    with open(file_path, "wb") as f:
        f.write(contents)

    asyncio.create_task(run_ocr_pipeline_task(task_id, file_path))
    asyncio.create_task(cleanup_task_resources(task_id))

    return {"task_id": task_id, "status": "pending"}


@router.get("/ocr/{task_id}")
async def get_task_status(task_id: str):
    from app.services.ocr_service import tasks_db

    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    from app.services.ocr_service import get_queue_position
    qp = get_queue_position(task_id) if task.status == "pending" else None
    return {
        "status": task.status,
        "phase": task.phase,
        "current": task.current,
        "total": task.total,
        "queue_position": qp,
        "page_errors": task.page_errors,
        "result": task.result,
        "translation": task.translation,
    }


@router.get("/ocr/{task_id}/result")
async def get_task_result(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in ("done", "error"):
        raise HTTPException(status_code=400, detail="Task is not yet complete")
    return OcrResult(
        task_id=task_id,
        full_text=task.result or "",
        pages=task.pages,
        page_errors=task.page_errors,
    )


@router.post("/ocr/{task_id}/translate")
async def start_translation(task_id: str):
    from app.services.ocr_service import tasks_db

    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "done":
        raise HTTPException(status_code=400, detail="OCR task is not yet complete")
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="Translation offline on this host")

    task.phase = "translating"

    try:
        blocks_by_key = {}
        for page in task.pages:
            for bi, block in enumerate(page.blocks):
                key = f"page-{page.page_number}-block-{bi}"
                block_text = " ".join(line.text for line in block.lines)
                blocks_by_key[key] = block_text

        if blocks_by_key:
            keys = list(blocks_by_key.keys())
            task.total = len(keys)
            task.current = 0
            all_translations: dict[str, str] = {}

            for start in range(0, len(keys), TRANSLATION_BATCH_SIZE):
                batch_keys = keys[start:start + TRANSLATION_BATCH_SIZE]
                batch_dict = {k: blocks_by_key[k] for k in batch_keys}
                batch_result = translate_blocks(batch_dict)
                all_translations.update(batch_result)
                task.current = min(start + TRANSLATION_BATCH_SIZE, len(keys))

            for page in task.pages:
                for bi, block in enumerate(page.blocks):
                    key = f"page-{page.page_number}-block-{bi}"
                    trans = all_translations.get(key, "")
                    for li, line in enumerate(block.lines):
                        line_key = f"{page.page_number}-{bi}-{li}"
                        task.line_translations[line_key] = trans

            task.translation = "done"
        else:
            translation = translate_devanagari_to_english(task.result or "")
            task.translation = translation

        task.phase = "completed"
        save_task_state(task_id)
    except Exception as e:
        task.translation_error = str(e)
        task.phase = "translation_failed"
        save_task_state(task_id)

    return {"status": "translating" if task.phase == "translating" else "done"}


@router.get("/ocr/{task_id}/translate")
async def get_translation_status(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.translation is not None:
        return {"status": "done", "translation": task.translation}
    if task.translation_error is not None:
        return {"status": "failed", "error": task.translation_error}
    return {"status": "translating"}


@router.get("/ocr/{task_id}/overlay")
async def get_overlay_data(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    page_data = []
    for p in task.pages:
        blocks_out = []
        for bi, block in enumerate(p.blocks):
            lines_out = []
            for li, line in enumerate(block.lines):
                line_key = f"{p.page_number}-{bi}-{li}"
                trans = task.line_translations.get(line_key, "")
                lines_out.append({
                    "text": line.text,
                    "translation": trans,
                    "x": line.x,
                    "y": line.y,
                    "width": line.width,
                    "height": line.height,
                })
            blocks_out.append({
                "lines": lines_out,
                "x": block.x,
                "y": block.y,
                "width": block.width,
                "height": block.height,
            })
        page_data.append({
            "page_number": p.page_number,
            "blocks": blocks_out,
        })
    return {"pages": page_data}


@router.get("/ocr/{task_id}/layers/{page_num}")
async def get_page_layer(task_id: str, page_num: int):
    page_path = os.path.join(UPLOAD_BASE, task_id, "pages", f"{page_num}.jpg")
    if not os.path.isfile(page_path):
        raise HTTPException(status_code=404, detail="Page image not found")
    return FileResponse(page_path, media_type="image/jpeg")


@router.delete("/ocr/{task_id}")
async def delete_task(task_id: str):
    from app.services.ocr_service import tasks_db
    task = tasks_db.get(task_id)
    if task:
        tasks_db.pop(task_id, None)
    task_dir = os.path.join(UPLOAD_BASE, task_id)
    if os.path.isdir(task_dir):
        import shutil
        shutil.rmtree(task_dir)
    return {"status": "cleaned"}
