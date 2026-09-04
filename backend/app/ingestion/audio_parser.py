import os
import logging
from pathlib import Path
from typing import Dict, Any
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

def parse_audio_recording(file_path: str) -> Dict[str, Any]:
    """Return genuine transcript segments or an explicit unavailable result."""
    path = Path(file_path)
    stem = path.stem
    file_size = os.path.getsize(file_path)
    chunks: List[Dict[str, Any]] = []

    # 1. Check if OpenAI Whisper API is available for neural transcription
    if settings.OPENAI_API_KEY and file_size < 25 * 1024 * 1024:
        try:
            with open(file_path, "rb") as f:
                files = {"file": (path.name, f, "audio/mpeg")}
                data = {"model": "whisper-1", "response_format": "verbose_json"}
                headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
                resp = httpx.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=60.0
                )
                if resp.status_code == 200:
                    result = resp.json()
                    segments = result.get("segments", [])
                    if segments:
                        for idx, seg in enumerate(segments):
                            start_ms = int(seg.get("start", 0) * 1000)
                            end_ms = int(seg.get("end", 0) * 1000)
                            text = seg.get("text", "").strip()
                            if text:
                                chunks.append({
                                    "content": text,
                                    "modality": "audio",
                                    "audio_start_ms": start_ms,
                                    "audio_end_ms": end_ms,
                                    "metadata": {
                            "segment_index": idx,
                                        "engine": "OpenAI-Whisper-1"
                                    }
                                })
                        if chunks:
                            return {"status": "TRANSCRIBED", "chunks": chunks, "metadata": {"transcription_engine": "OpenAI-Whisper-1"}}
        except Exception as e:
            logger.warning("Whisper transcription failed (%s); semantic transcription is unavailable", e)

    return {
        "status": "TRANSCRIPTION_UNAVAILABLE",
        "chunks": [],
        "metadata": {"file_size_bytes": file_size, "transcription_status": "TRANSCRIPTION_UNAVAILABLE"},
    }
