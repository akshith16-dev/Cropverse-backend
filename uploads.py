from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from auth import get_current_user
from config import settings
from storage import storage

UPLOAD_DIR = Path(__file__).with_name("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_DOCUMENTS = {"application/pdf", "text/plain", "text/csv", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
router = APIRouter(prefix="/upload", tags=["Uploads"])

def _looks_like_image(content: bytes, content_type: str) -> bool:
    signatures = {
        "image/jpeg": (b"\xff\xd8\xff",),
        "image/png": (b"\x89PNG\r\n\x1a\n",),
        "image/webp": (b"RIFF",),
    }
    return any(content.startswith(signature) for signature in signatures.get(content_type, ()))

def _looks_like_document(content: bytes, content_type: str) -> bool:
    if content_type == "application/pdf":
        return content.startswith(b"%PDF")
    if content_type in {"text/plain", "text/csv"}:
        try:
            content[:2048].decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return content.startswith(b"PK")
    return False

async def _save(file: UploadFile, accepted: set[str], folder: str) -> dict:
    if file.content_type not in accepted:
        raise HTTPException(415, "Unsupported file type")
    content = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(content) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File must be 10 MB or smaller")
    if folder == "images" and not _looks_like_image(content, file.content_type):
        raise HTTPException(400, "Invalid image file")
    if folder == "documents" and not _looks_like_document(content, file.content_type):
        raise HTTPException(400, "Invalid document file")
    url = await storage.save(content, file.filename or "upload", file.content_type, folder)
    return {
        "filename": file.filename,
        "url": url,
        "content_type": file.content_type,
        "storage": "s3" if storage.using_s3 else "local",
    }

@router.post("/image")
async def upload_image(file: UploadFile = File(...), _=Depends(get_current_user)):
    return await _save(file, ALLOWED_IMAGES, "images")

@router.post("/document")
async def upload_document(file: UploadFile = File(...), _=Depends(get_current_user)):
    return await _save(file, ALLOWED_DOCUMENTS, "documents")
