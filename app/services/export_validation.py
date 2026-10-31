"""Validate exported PDF/DOCX files before the user can download them.

The PDF is read back with pypdf and the DOCX with python-docx, i.e. independently of the
libraries that wrote them, the way an ATS would read them.
"""
from __future__ import annotations

import io
import re
from typing import Any

from docx import Document
from docx.shared import Pt

from app.services.resume_export import Block, block_text, build_blocks, pdf_text
from app.services.resume_structure import Resume

ALLOWED_FONT_PREFIXES = ("helvetica", "arial", "times", "calibri", "courier", "liberation", "dejavu")
Check = dict[str, Any]


def _check(label: str, ok: bool, detail: str = "") -> Check:
    return {"label": label, "ok": bool(ok), "detail": detail}


def _norm(text: str) -> str:
    text = pdf_text(text).replace("•", " ")
    return " ".join(text.split()).casefold()


def _group(checks: list[Check], **extra: Any) -> dict[str, Any]:
    return {"ok": all(c["ok"] for c in checks), "checks": checks, **extra}


def validate_content(resume: Resume) -> dict[str, Any]:
    blocks = build_blocks(resume)
    headings = [b for b in blocks if b["kind"] == "heading"]
    checks = [
        _check("Candidate name present", bool(resume["name"].strip()),
               "" if resume["name"].strip() else "Add your name in the editor."),
        _check("Contact details present in the document body",
               bool(resume["email"].strip() or resume["phone"].strip()),
               "" if (resume["email"].strip() or resume["phone"].strip()) else "Add an email or phone number."),
        _check("At least one standard section", bool(headings)),
    ]
    return _group(checks)


# --- PDF ------------------------------------------------------------------------------------------

def _pdf_read(data: bytes) -> tuple[Any, list[str]]:
    from pypdf import PdfReader  # imported lazily so the rest of the app doesn't need it at import time

    reader = PdfReader(io.BytesIO(data))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return reader, pages


def pdf_text_of(data: bytes) -> str:
    """Text of a PDF as an independent reader sees it (used by tests and validation)."""
    return "\n".join(_pdf_read(data)[1])


def _in_order(lines: list[str], headings: list[str]) -> tuple[bool, str]:
    pos = 0
    normalized = [_norm(line) for line in lines]
    for heading in headings:
        target = _norm(heading)
        try:
            pos = normalized.index(target, pos) + 1
        except ValueError:
            return False, f"Heading '{heading}' not found in order."
    return True, ""


def validate_pdf(blocks: list[Block], data: bytes) -> dict[str, Any]:
    checks: list[Check] = []
    pages = 0
    try:
        reader, page_texts = _pdf_read(data)
    except Exception:
        return _group([_check("PDF can be opened and read", False, "The PDF could not be read back.")], pages=0)
    pages = len(reader.pages)
    text = "\n".join(page_texts)
    flat = _norm(text)

    checks.append(_check("Valid PDF file", data[:5] == b"%PDF-" and not reader.is_encrypted))
    checks.append(_check("Selectable, extractable text", len(flat) > 20,
                         f"{len(flat.split())} words extracted"))
    missing = [block_text(b) for b in blocks if _norm(block_text(b)) not in flat]
    checks.append(_check("All resume content present in the PDF text", not missing,
                         "" if not missing else f"Missing: {missing[0][:60]}"))
    headings = [b["text"] for b in blocks if b["kind"] == "heading"]
    ok, detail = _in_order(text.splitlines(), headings)
    checks.append(_check("Section headings present and in order", ok, detail))

    fonts, has_image = set(), False
    for page in reader.pages:
        resources = page.get("/Resources")
        resources = resources.get_object() if resources is not None else {}
        font_dict = resources.get("/Font")
        if font_dict is not None:
            for obj in font_dict.get_object().values():
                fonts.add(str(obj.get_object().get("/BaseFont", "")).lstrip("/").split("+")[-1])
        xobjects = resources.get("/XObject")
        if xobjects is not None:
            has_image = has_image or any(
                str(x.get_object().get("/Subtype")) == "/Image" for x in xobjects.get_object().values()
            )
    standard = bool(fonts) and all(f.lower().startswith(ALLOWED_FONT_PREFIXES) for f in fonts)
    checks.append(_check("Standard fonts only", standard, ", ".join(sorted(fonts))))
    checks.append(_check("No images or graphics", not has_image))
    checks.append(_check("Length is 1-2 pages", 1 <= pages <= 2, f"{pages} page{'s' if pages != 1 else ''}"))
    return _group(checks, pages=pages)


# --- DOCX -----------------------------------------------------------------------------------------

def _docx_read(data: bytes) -> Any:
    return Document(io.BytesIO(data))


def docx_text_of(data: bytes) -> str:
    return "\n".join(p.text for p in _docx_read(data).paragraphs)


def validate_docx(blocks: list[Block], data: bytes) -> dict[str, Any]:
    try:
        doc = _docx_read(data)
    except Exception:
        return _group([_check("DOCX can be opened and read", False, "The DOCX could not be read back.")])
    checks: list[Check] = [_check("Valid, editable DOCX file", True)]
    paragraphs = doc.paragraphs
    texts = [p.text for p in paragraphs]
    flat = _norm("\n".join(texts))
    xml = doc.element.xml

    missing = [block_text(b) for b in blocks if _norm(block_text(b)) not in flat]
    checks.append(_check("All resume content present in the DOCX text", not missing,
                         "" if not missing else f"Missing: {missing[0][:60]}"))
    expected_headings = [b["text"] for b in blocks if b["kind"] == "heading"]
    actual_headings = [p.text for p in paragraphs if p.style.name == "Heading 1"]
    checks.append(_check("Section headings present and in order", actual_headings == expected_headings,
                         "" if actual_headings == expected_headings else "Headings differ from expected order."))
    expected_bullets = sum(1 for b in blocks if b["kind"] == "bullet")
    actual_bullets = sum(1 for p in paragraphs if p.style.name == "List Bullet")
    checks.append(_check("Conventional bullet points", expected_bullets == actual_bullets,
                         f"{actual_bullets} bullets"))
    checks.append(_check("No tables", len(doc.tables) == 0 and "<w:tbl>" not in xml))
    checks.append(_check("No text boxes, images or shapes",
                         not any(tag in xml for tag in ("w:txbxContent", "w:drawing", "w:pict")) and not doc.inline_shapes))
    header_footer = [p.text for s in doc.sections for p in (*s.header.paragraphs, *s.footer.paragraphs)]
    checks.append(_check("Contact details are in the body, not a header/footer", not any(t.strip() for t in header_footer)))
    normal = doc.styles["Normal"].font
    font_ok = (normal.name or "").lower().startswith(ALLOWED_FONT_PREFIXES) and (normal.size or 0) >= Pt(9)
    checks.append(_check("Standard font and readable size", font_ok,
                         f"{normal.name}, {normal.size.pt if normal.size else '?'} pt"))
    return _group(checks)


# --- Combined -----------------------------------------------------------------------------------------

def _words(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", _norm(text)).split()


def validate_exports(resume: Resume, pdf_bytes: bytes, docx_bytes: bytes) -> dict[str, Any]:
    blocks = build_blocks(resume)
    content = validate_content(resume)
    pdf = validate_pdf(blocks, pdf_bytes)
    docx = validate_docx(blocks, docx_bytes)
    try:
        same = _words(pdf_text_of(pdf_bytes)) == _words(docx_text_of(docx_bytes))
        cross = _group([_check("PDF and DOCX contain the same words in the same order", same)])
    except Exception:
        cross = _group([_check("PDF and DOCX contain the same words in the same order", False, "Comparison failed.")])
    return {
        "ok": content["ok"] and pdf["ok"] and docx["ok"] and cross["ok"],
        "content": content, "pdf": pdf, "docx": docx, "cross": cross,
    }
