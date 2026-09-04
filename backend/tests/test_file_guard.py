import pytest
from io import BytesIO
from fastapi import UploadFile, HTTPException
from app.ingestion.file_guard import (
    sanitize_filename, 
    validate_magic_bytes, 
    detect_modality, 
    process_and_save_upload
)

def test_filename_sanitization_path_traversal():
    # Attempt directory traversal and special chars
    malicious_names = [
        "../../etc/passwd",
        "..\\..\\windows\\system32\\cmd.exe",
        "nested/path/to/financials.pdf",
        "../../../secret_keys.json",
        "__test__<>:\"|?*.csv"
    ]
    for name in malicious_names:
        clean = sanitize_filename(name)
        assert "/" not in clean
        assert "\\" not in clean
        assert ".." not in clean

def test_magic_byte_validation():
    # PDF magic byte
    pdf_header = b"%PDF-1.7 standard document header"
    assert validate_magic_bytes(pdf_header, ".pdf") is True

    # Spoofed PDF (actually an executable)
    fake_pdf = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00"
    assert validate_magic_bytes(fake_pdf, ".pdf") is False

    # PNG magic byte
    png_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    assert validate_magic_bytes(png_header, ".png") is True

    # Audio magic bytes: MP3, WAV, M4A, OGG
    mp3_id3 = b"ID3\x03\x00\x00\x00\x00\x00\x00"
    assert validate_magic_bytes(mp3_id3, ".mp3") is True

    mp3_raw = b"\xff\xfb\x90\x44"
    assert validate_magic_bytes(mp3_raw, ".mp3") is True

    wav_header = b"RIFF\x24\x00\x00\x00WAVE"
    assert validate_magic_bytes(wav_header, ".wav") is True

    m4a_header = b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00"
    assert validate_magic_bytes(m4a_header, ".m4a") is True

    ogg_header = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00"
    assert validate_magic_bytes(ogg_header, ".ogg") is True

    # Spoofed audio (fake text disguised as mp3)
    fake_mp3 = b"This is not a real mp3 file"
    assert validate_magic_bytes(fake_mp3, ".mp3") is False
    assert validate_magic_bytes(fake_mp3, ".wav") is False
    assert validate_magic_bytes(fake_mp3, ".m4a") is False
    assert validate_magic_bytes(fake_mp3, ".ogg") is False

def test_detect_modality():
    assert detect_modality(".pdf", "application/pdf") == "pdf"
    assert detect_modality(".xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") == "spreadsheet"
    assert detect_modality(".csv", "text/csv") == "spreadsheet"
    assert detect_modality(".mp3", "audio/mpeg") == "audio"
    assert detect_modality(".wav", "audio/wav") == "audio"
    assert detect_modality(".m4a", "audio/m4a") == "audio"
    assert detect_modality(".ogg", "audio/ogg") == "audio"
    assert detect_modality(".png", "image/png") == "image"
    assert detect_modality(".jpg", "image/jpeg") == "image"
