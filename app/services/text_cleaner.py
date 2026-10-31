"""Text normalization helpers."""
from __future__ import annotations

import re
import unicodedata

_BULLETS = re.compile(r"[•‣◦⁃∙▪●·]")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d")


def clean_text(text: str, keep_lines: bool = False) -> str:
    """Normalize unicode, bullets and whitespace.

    Case is preserved (for evidence display); matching uses case-insensitive
    regexes. With keep_lines=True, line breaks survive (needed to detect the
    section headings of a job description).
    """
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\r", "\n").replace(" ", " ")
    text = _BULLETS.sub(" ", text)
    if keep_lines:
        lines = (" ".join(line.split()) for line in text.split("\n"))
        return "\n".join(line for line in lines if line)
    return " ".join(text.split())


def redact_contact_details(snippet: str) -> str:
    """Hide emails and phone numbers in snippets shown as evidence."""
    return _PHONE.sub("[redacted]", _EMAIL.sub("[redacted]", snippet))
