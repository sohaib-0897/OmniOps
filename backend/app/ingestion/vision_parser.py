import os
import logging
from pathlib import Path
from typing import Dict, Any
import struct
from app.core.config import settings

logger = logging.getLogger(__name__)

def parse_image_file(file_path: str) -> Dict[str, Any]:
    """Extract deterministic file properties without inventing image semantics."""
    path = Path(file_path)
    stem = path.stem
    file_size = os.path.getsize(file_path)
    width = height = None
    image_type = None
    try:
        with open(file_path, "rb") as f:
            header = f.read(64)
            if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
                image_type = "png"
                width, height = struct.unpack(">II", header[16:24])
            elif header.startswith(b"\xff\xd8"):
                image_type = "jpeg"
    except Exception:
        pass

    return {
        "status": "VISION_ANALYSIS_UNAVAILABLE",
        "chunks": [],
        "metadata": {
            "file_name": path.name,
            "file_type": image_type or path.suffix.lower().lstrip("."),
            "width": width,
            "height": height,
            "file_size_bytes": file_size,
            "vision_status": "VISION_ANALYSIS_UNAVAILABLE",
        },
    }
