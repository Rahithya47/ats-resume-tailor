"""Input validation for uploads and form fields."""
from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class InputError(Exception):
    """A user-facing validation problem. The message is safe to display."""


def validate_upload(file_storage) -> str:
    """Check presence and extension of the upload. Returns the lowercase extension."""
    if file_storage is None or not getattr(file_storage, "filename", ""):
        raise InputError("Please choose a resume file (PDF or DOCX).")
    ext = Path(file_storage.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InputError("Unsupported file type. Please upload a .pdf or .docx file.")
    return ext


def check_file_size(path: str, max_bytes: int) -> None:
    size = os.path.getsize(path)
    if size == 0:
        raise InputError("The uploaded file is empty.")
    if size > max_bytes:
        raise InputError(f"The file is too large. The limit is {max_bytes / (1024 * 1024):g} MB.")


def check_signature(path: str, ext: str) -> None:
    """Verify the file content matches its extension (not just the name)."""
    if ext == ".pdf":
        with open(path, "rb") as handle:
            head = handle.read(1024)
        if b"%PDF-" not in head:
            raise InputError("This file does not look like a valid PDF.")
    elif ext == ".docx":
        try:
            with zipfile.ZipFile(path) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise InputError("This file is not a valid DOCX document.")
        except zipfile.BadZipFile as exc:
            raise InputError(
                "This file is not a valid DOCX. It may be corrupted or password-protected."
            ) from exc


def validate_job_description(text: str, min_chars: int, max_chars: int) -> str:
    cleaned = _CONTROL_CHARS.sub("", text or "").strip()
    if not cleaned:
        raise InputError("Please paste the job description.")
    if len(cleaned) < min_chars:
        raise InputError("The job description is too short to analyze. Paste the full posting.")
    if len(cleaned) > max_chars:
        raise InputError(f"The job description is too long (maximum {max_chars:,} characters).")
    return cleaned


def validate_optional_field(value: str, label: str, max_chars: int) -> str:
    cleaned = " ".join(_CONTROL_CHARS.sub("", value or "").split())
    if len(cleaned) > max_chars:
        raise InputError(f"{label} must be at most {max_chars} characters.")
    return cleaned
