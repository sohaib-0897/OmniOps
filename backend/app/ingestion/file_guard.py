import os
import re
import hashlib
import zipfile
from pathlib import Path
from typing import Tuple, Dict
from fastapi import UploadFile, HTTPException, status
from app.core.config import settings

# Magic byte signatures for authorized file types
MAGIC_SIGNATURES: Dict[str, bytes] = {
    "pdf": b"%PDF",
    "docx": b"PK\x03\x04",  # Zip-based XML
    "xlsx": b"PK\x03\x04",  # Zip-based XML
    "png": b"\x89PNG\r\n\x1a\n",
    "jpg": b"\xff\xd8\xff",
    "mp3_id3": b"ID3",
    "mp3_raw": b"\xff\xfb",
    "wav": b"RIFF",
    "ogg": b"OggS",
}

def sanitize_filename(raw_filename: str) -> str:
    """Sanitize filename to prevent directory traversal and special character attacks."""
    base_name = Path(raw_filename).name
    # Strip any leading dots or paths
    clean_name = re.sub(r"[^a-zA-Z0-9_\-\. ]", "_", base_name)
    clean_name = re.sub(r"\.{2,}", ".", clean_name)
    if not clean_name or clean_name.startswith("."):
        clean_name = f"upload_{os.urandom(4).hex()}_{clean_name.lstrip('.')}"
    return clean_name

def detect_modality(extension: str, mime_type: str) -> str:
    """Classify file into standard business modality."""
    ext = extension.lower()
    if ext == ".pdf":
        return "pdf"
    elif ext in [".docx", ".doc"]:
        return "docx"
    elif ext in [".xlsx", ".xls", ".csv", ".tsv"]:
        return "spreadsheet"
    elif ext in [".mp3", ".wav", ".m4a", ".ogg"]:
        return "audio"
    elif ext in [".png", ".jpg", ".jpeg"]:
        return "image"
    elif ext in [".txt", ".md"]:
        return "text"
    return "text"

def validate_magic_bytes(header: bytes, ext: str) -> bool:
    """Validate file binary header against expected magic bytes."""
    ext = ext.lower()
    if ext == ".pdf":
        return header.startswith(MAGIC_SIGNATURES["pdf"])
    elif ext in [".docx", ".xlsx"]:
        return header.startswith(MAGIC_SIGNATURES["docx"])
    elif ext == ".png":
        return header.startswith(MAGIC_SIGNATURES["png"])
    elif ext in [".jpg", ".jpeg"]:
        return header.startswith(MAGIC_SIGNATURES["jpg"])
    elif ext == ".mp3":
        return header.startswith(MAGIC_SIGNATURES["mp3_id3"]) or header.startswith(MAGIC_SIGNATURES["mp3_raw"]) or header.startswith(b"\xff\xf3") or header.startswith(b"\xff\xf2")
    elif ext == ".wav":
        return header.startswith(MAGIC_SIGNATURES["wav"])
    elif ext == ".m4a":
        return b"ftyp" in header[:32]
    elif ext == ".ogg":
        return header.startswith(MAGIC_SIGNATURES["ogg"])
    elif ext in [".csv", ".tsv", ".txt", ".md"]:
        # Plaintext validation: ensure no binary null bytes in initial chunk
        return b"\x00" not in header[:512]
    return True

async def process_and_save_upload(
    file: UploadFile,
    workspace_id: str
) -> Tuple[str, str, int, str, str]:
    """Securely inspect, hash, and store uploaded file.
    Returns: (clean_filename, storage_path, byte_size, sha256_hash, modality)
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must have a valid filename."
        )
    
    clean_filename = sanitize_filename(file.filename)
    ext = Path(clean_filename).suffix.lower()
    
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not supported. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )
    
    # Read initial header for magic byte inspection
    header = await file.read(1024)
    if not header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )
    
    if not validate_magic_bytes(header, ext):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MIME/Magic-byte validation failed: File content does not match extension '{ext}'."
        )
    
    # Reset read pointer and compute full hash & size
    await file.seek(0)
    hasher = hashlib.sha256()
    byte_count = 0
    
    workspace_dir = settings.UPLOAD_DIR / str(workspace_id)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    temp_target_path = workspace_dir / f"tmp_{os.urandom(8).hex()}_{clean_filename}"
    
    with open(temp_target_path, "wb") as f:
        while chunk := await file.read(64 * 1024):
            byte_count += len(chunk)
            if byte_count > settings.MAX_FILE_SIZE_BYTES:
                temp_target_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File size exceeds maximum allowed limit of {settings.MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
                )
            hasher.update(chunk)
            f.write(chunk)
            
    sha256_hash = hasher.hexdigest()
    final_filename = f"{sha256_hash[:12]}_{clean_filename}"
    final_storage_path = workspace_dir / final_filename
    
    if final_storage_path.exists():
        # Deduplicated file already exists
        temp_target_path.unlink(missing_ok=True)
    else:
        temp_target_path.rename(final_storage_path)

    if ext in {".docx", ".xlsx"}:
        try:
            with zipfile.ZipFile(final_storage_path) as archive:
                members = archive.infolist()
                total = sum(item.file_size for item in members)
                if total > settings.MAX_UNCOMPRESSED_BYTES or total > max(byte_count * 100, 10 * 1024 * 1024):
                    raise ValueError("Office archive expansion limit exceeded.")
                for item in members:
                    normalized = item.filename.replace("\\", "/")
                    if normalized.startswith("/") or "../" in f"/{normalized}" or normalized.lower().endswith("vbaproject.bin"):
                        raise ValueError("Unsafe path or macro content in Office document.")
        except (zipfile.BadZipFile, ValueError) as exc:
            final_storage_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Invalid or unsafe Office document: {exc}")
        
    modality = detect_modality(ext, file.content_type or "")
    return clean_filename, str(final_storage_path), byte_count, sha256_hash, modality
