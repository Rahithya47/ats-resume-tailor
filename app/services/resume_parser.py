"""Extract plain text from PDF and DOCX resumes."""
from __future__ import annotations

from app.validators import InputError

try:  # PyMuPDF >= 1.24.3 exposes `pymupdf`; older versions expose `fitz`.
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from docx import Document

MAX_TEXT_CHARS = 300_000


class ResumeParseError(InputError):
    """The file could not be turned into usable text."""


def extract_pdf_text(path: str) -> str:
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise ResumeParseError("This PDF could not be opened. It may be corrupted.") from exc
    try:
        if doc.needs_pass or doc.is_encrypted:
            raise ResumeParseError(
                "This PDF is password-protected. Remove the password and upload it again."
            )
        parts = [page.get_text("text") for page in doc]
    except ResumeParseError:
        raise
    except Exception as exc:
        raise ResumeParseError("Text could not be read from this PDF.") from exc
    finally:
        doc.close()
    text = "\n".join(parts).strip()
    if not text:
        raise ResumeParseError(
            "No selectable text was found. This looks like a scanned or image-only PDF. "
            "OCR is not supported yet; export a text-based PDF or upload a DOCX instead."
        )
    return text[:MAX_TEXT_CHARS]


def extract_docx_text(path: str) -> str:
    try:
        document = Document(path)
    except Exception as exc:
        raise ResumeParseError("This DOCX could not be opened. It may be corrupted.") from exc
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    text = "\n".join(parts).strip()
    if not text:
        raise ResumeParseError("No text was found in this DOCX document.")
    return text[:MAX_TEXT_CHARS]


def extract_resume_text(path: str, ext: str) -> str:
    if ext == ".pdf":
        return extract_pdf_text(path)
    if ext == ".docx":
        return extract_docx_text(path)
    raise ResumeParseError("Unsupported file type.")
