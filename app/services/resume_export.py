"""Build the ATS-friendly PDF and DOCX from ONE shared list of blocks.

Both files are generated from `build_blocks(resume)`, so they always contain the same
content in the same order. Layout rules (for ATS parsing): single column, standard fonts,
real text, conventional bullets, standard section headings, no tables, text boxes,
images, icons, rules or header/footer content. Contact details live in the body.
"""
from __future__ import annotations

import io
import re
import unicodedata
from typing import Any
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate

from app.services.resume_structure import Resume, normalize_dates

SECTION_ORDER = [
    ("summary", "Professional Summary"),
    ("skills", "Technical Skills"),
    ("projects", "Projects"),
    ("experience", "Experience"),
    ("education", "Education"),
    ("certifications", "Certifications"),
]
DOCX_FONT = "Arial"          # PDF uses Helvetica, its metric-compatible equivalent
PDF_FONT_SIZES = (10.5, 10.0, 9.5)  # shrink slightly to reach one page; never below 9.5 pt

Block = dict[str, str]


def block_text(block: Block) -> str:
    if block["kind"] == "skill" and block.get("label"):
        return f"{block['label']}: {block['text']}"
    return block["text"]


def build_blocks(resume: Resume) -> list[Block]:
    """The single source of truth for what appears in the exported files and the preview."""
    blocks: list[Block] = []

    def add(kind: str, text: str, label: str = "") -> None:
        text = text.strip()
        if text:
            blocks.append({"kind": kind, "text": text, "label": label})

    add("name", resume["name"])
    add("headline", resume["headline"])
    add("contact", " | ".join(p for p in (resume["email"], resume["phone"], resume["location"]) if p))
    add("links", " | ".join(resume["links"]))

    for key, title in SECTION_ORDER:
        if key == "summary":
            if resume["summary"].strip():
                add("heading", title)
                add("paragraph", resume["summary"])
        elif key == "skills":
            groups = [g for g in resume["skills"] if g["items"]]
            if groups:
                add("heading", title)
                for g in groups:
                    add("skill", ", ".join(g["items"]), label=g["category"].strip())
        elif key == "certifications":
            if resume["certifications"]:
                add("heading", title)
                for line in resume["certifications"]:
                    add("detail", line)
        else:
            entries = [e for e in resume[key] if e["heading"] or e["details"] or e["bullets"]]
            if entries:
                add("heading", title)
                for e in entries:
                    add("entry_heading", normalize_dates(e["heading"]))
                    for d in e["details"]:
                        add("detail", normalize_dates(d))
                    for b in e["bullets"]:
                        add("bullet", b)
    for extra in resume["extras"]:
        if extra["lines"]:
            add("heading", extra["title"])
            for line in extra["lines"]:
                add("bullet", line)
    return blocks


def plain_text(resume: Resume) -> str:
    return "\n".join(block_text(b) for b in build_blocks(resume))


def safe_filename(resume: Resume, ext: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "_", unicodedata.normalize("NFKD", resume.get("name", ""))
                  .encode("ascii", "ignore").decode()).strip("_")
    return f"{base or 'Candidate'}_Tailored_Resume.{ext}"


# --- PDF ---------------------------------------------------------------------------------

_PDF_REPLACEMENTS = {
    "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
    "−": "-", "…": "...", " ": " ",
}


def pdf_text(text: str) -> str:
    """Make text safe for the PDF's standard (WinAnsi) fonts: smart punctuation to ASCII,
    accents stripped when a glyph is unavailable, unsupported characters shown as '?'."""
    text = unicodedata.normalize("NFKC", text)
    for src, dst in _PDF_REPLACEMENTS.items():
        text = text.replace(src, dst)
    out = []
    for ch in text:
        try:
            ch.encode("cp1252")
            out.append(ch)
        except UnicodeEncodeError:
            base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
            try:
                base.encode("cp1252")
                out.append(base)
            except UnicodeEncodeError:
                out.append("?")
    return "".join(out)


def _pdf_styles(size: float) -> dict[str, ParagraphStyle]:
    lead = size * 1.28
    base = dict(fontName="Helvetica", fontSize=size, leading=lead, spaceAfter=1.5)
    return {
        "name": ParagraphStyle("name", fontName="Helvetica-Bold", fontSize=size + 6, leading=(size + 6) * 1.2,
                               alignment=TA_CENTER, spaceAfter=2),
        "headline": ParagraphStyle("headline", alignment=TA_CENTER, **base),
        "contact": ParagraphStyle("contact", alignment=TA_CENTER, **base),
        "links": ParagraphStyle("links", alignment=TA_CENTER, **base),
        "heading": ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=size + 1, leading=(size + 1) * 1.3,
                                  spaceBefore=size * 0.9, spaceAfter=2.5, keepWithNext=1),
        "paragraph": ParagraphStyle("paragraph", **base),
        "skill": ParagraphStyle("skill", **base),
        "entry_heading": ParagraphStyle("entry_heading", fontName="Helvetica-Bold", fontSize=size, leading=lead,
                                        spaceBefore=3.5, spaceAfter=1, keepWithNext=1),
        "detail": ParagraphStyle("detail", **base),
        "bullet": ParagraphStyle("bullet", leftIndent=14, bulletIndent=3, **base),
    }


def _render_pdf(blocks: list[Block], size: float, title: str, author: str) -> tuple[bytes, int]:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch, title=title, author=author, subject="Resume",
    )
    styles = _pdf_styles(size)
    story = []
    for block in blocks:
        text = escape(pdf_text(block["text"]))
        kind = block["kind"]
        if kind == "skill" and block.get("label"):
            text = f"<b>{escape(pdf_text(block['label']))}:</b> {text}"
        if kind == "bullet":
            story.append(Paragraph(text, styles["bullet"], bulletText="•"))
        else:
            story.append(Paragraph(text, styles[kind]))
    doc.build(story)
    return buffer.getvalue(), int(doc.page)


def build_pdf(resume: Resume) -> bytes:
    blocks = build_blocks(resume)
    title = f"{resume['name']} - Resume" if resume["name"] else "Resume"
    data = b""
    for size in PDF_FONT_SIZES:
        data, pages = _render_pdf(blocks, size, title, resume["name"])
        if pages <= 1:
            break
    return data


# --- DOCX --------------------------------------------------------------------------------

def _set_style_font(style: Any, size: float, bold: bool | None = None) -> None:
    style.font.name = DOCX_FONT
    style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    style.font.color.rgb = RGBColor(0, 0, 0)
    fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        fonts.attrib.pop(qn(f"w:{attr}"), None)  # theme fonts would override the explicit font
    for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
        fonts.set(qn(f"w:{attr}"), DOCX_FONT)


def build_docx(resume: Resume) -> bytes:
    blocks = build_blocks(resume)
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.27), Inches(11.69)  # A4
    section.left_margin = section.right_margin = Inches(0.75)
    section.top_margin = section.bottom_margin = Inches(0.6)

    normal = doc.styles["Normal"]
    _set_style_font(normal, 10.5)
    normal.paragraph_format.space_after = Pt(2)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.line_spacing = 1.1

    heading = doc.styles["Heading 1"]
    _set_style_font(heading, 11.5, bold=True)
    heading.paragraph_format.space_before = Pt(9)
    heading.paragraph_format.space_after = Pt(3)
    heading.paragraph_format.keep_with_next = True

    bullet = doc.styles["List Bullet"]
    _set_style_font(bullet, 10.5)
    bullet.paragraph_format.space_after = Pt(1.5)

    for block in blocks:
        kind, text = block["kind"], block["text"]
        if kind == "heading":
            doc.add_paragraph(text, style="Heading 1")
        elif kind == "bullet":
            doc.add_paragraph(text, style="List Bullet")
        elif kind == "name":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(text)
            run.bold = True
            run.font.size = Pt(16.5)
        elif kind in ("headline", "contact", "links"):
            p = doc.add_paragraph(text)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif kind == "entry_heading":
            p = doc.add_paragraph()
            p.add_run(text).bold = True
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.keep_with_next = True
        elif kind == "skill" and block.get("label"):
            p = doc.add_paragraph()
            p.add_run(f"{block['label']}:").bold = True
            p.add_run(f" {text}")
        else:
            doc.add_paragraph(text)

    props = doc.core_properties
    props.title = f"{resume['name']} - Resume" if resume["name"] else "Resume"
    props.author = resume["name"]
    props.subject = "Resume"
    props.comments = ""
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
