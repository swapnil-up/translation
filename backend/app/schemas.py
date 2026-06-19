from pydantic import BaseModel
from typing import Optional


class OcrWord(BaseModel):
    text: str
    x: int
    y: int
    width: int
    height: int


class OcrPage(BaseModel):
    page_number: int
    text: str
    words: list[OcrWord]
    status: str  # "success" | "blank" | "failed"


class OcrTaskState(BaseModel):
    status: str  # "pending" | "processing" | "done" | "error"
    phase: str   # "queued" | "converting_pdf" | "ocr" | "translating" | "completed" | "failed"
    current: int
    total: int
    queue_position: Optional[int] = None
    pages: list[OcrPage] = []
    page_errors: dict[int, str] = {}
    result: Optional[str] = None
    translation: Optional[str] = None
    translation_error: Optional[str] = None
    error: Optional[str] = None


class OcrResult(BaseModel):
    task_id: str
    full_text: str
    pages: list[OcrPage]
    page_errors: dict[int, str]


class ConfigStatus(BaseModel):
    ocr_enabled: bool = True
    translation_enabled: bool = False
