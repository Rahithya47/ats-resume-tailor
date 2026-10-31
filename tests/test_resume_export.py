import io

import pytest
from docx import Document

from app.context_store import ContextStore
from app.services.export_validation import docx_text_of, pdf_text_of, validate_exports
from app.services.keyword_extractor import extract_job_terms
from app.services.resume_edit import form_to_resume, resume_to_form
from app.services.resume_export import build_blocks, build_docx, build_pdf, safe_filename
from app.services.resume_structure import empty_resume, parse_resume
from app.services.tailoring import tailor_resume
from tests.conftest import SAMPLE_JD, SAMPLE_RESUME


@pytest.fixture
def draft():
    terms = extract_job_terms(SAMPLE_JD)
    return tailor_resume(parse_resume(SAMPLE_RESUME), terms["required"], terms["preferred"])[0]


# --- blocks / filenames ---------------------------------------------------------------------------

def test_section_order_and_empty_sections_omitted(draft):
    draft["certifications"] = []
    headings = [b["text"] for b in build_blocks(draft) if b["kind"] == "heading"]
    assert headings == ["Professional Summary", "Technical Skills", "Projects", "Experience", "Education"]


def test_contact_details_are_in_the_body_blocks(draft):
    kinds = {b["kind"]: b["text"] for b in build_blocks(draft)}
    assert "rahithya@example.com" in kinds["contact"] and "+91 98765 43210" in kinds["contact"]
    assert "github.com/rahithya" in kinds["links"]


@pytest.mark.parametrize("name,expected", [
    ("Rahithya K", "Rahithya_K_Tailored_Resume.pdf"),
    ("José Müller", "Jose_Muller_Tailored_Resume.pdf"),
    ("../../etc/passwd", "etc_passwd_Tailored_Resume.pdf"),
    ("", "Candidate_Tailored_Resume.pdf"),
])
def test_safe_filename(name, expected):
    assert safe_filename({"name": name}, "pdf") == expected


# --- PDF ----------------------------------------------------------------------------------------------

def test_pdf_is_a_real_text_pdf(draft):
    data = build_pdf(draft)
    assert data.startswith(b"%PDF-")
    text = pdf_text_of(data)
    for expected in ("Rahithya K", "Professional Summary", "Technical Skills", "Python, SQL, JavaScript",
                     "Wrote unit tests with pytest covering core routes", "Jun 2024 - Aug 2024"):
        assert expected in text
    order = [text.index(h) for h in ("Professional Summary", "Technical Skills", "Projects",
                                     "Experience", "Education", "Certifications")]
    assert order == sorted(order)


def test_pdf_special_characters_are_escaped_and_extractable(draft):
    draft["summary"] = "Worked on R&D <b>tools</b> & more"
    assert "R&D <b>tools</b> & more" in pdf_text_of(build_pdf(draft))


def test_pdf_handles_non_latin_text_without_failing(draft):
    draft["skills"].append({"category": "Languages", "items": ["हिंदी", "English"]})
    pdf, docx = build_pdf(draft), build_docx(draft)
    assert validate_exports(draft, pdf, docx)["ok"]
    assert "हिंदी" in docx_text_of(docx)  # DOCX keeps the original characters


# --- DOCX ---------------------------------------------------------------------------------------------

def test_docx_structure_is_ats_friendly(draft):
    doc = Document(io.BytesIO(build_docx(draft)))
    assert doc.tables == [] and not doc.inline_shapes
    assert [p.text for p in doc.paragraphs if p.style.name == "Heading 1"] == [
        "Professional Summary", "Technical Skills", "Projects", "Experience", "Education", "Certifications"]
    assert sum(1 for p in doc.paragraphs if p.style.name == "List Bullet") == 5
    assert all(not p.text.strip() for s in doc.sections for p in (*s.header.paragraphs, *s.footer.paragraphs))
    assert "rahithya@example.com" in "\n".join(p.text for p in doc.paragraphs)
    assert doc.styles["Normal"].font.name == "Arial"
    for tag in ("w:tbl", "w:txbxContent", "w:drawing", "w:pict"):
        assert tag not in doc.element.xml


def test_docx_is_editable_and_matches_pdf_content(draft):
    pdf, docx = build_pdf(draft), build_docx(draft)
    assert validate_exports(draft, pdf, docx)["cross"]["ok"]
    # Editable: python-docx can open it, change a paragraph and save it again.
    document = Document(io.BytesIO(docx))
    document.paragraphs[0].text = "Edited Name"
    out = io.BytesIO()
    document.save(out)
    assert "Edited Name" in docx_text_of(out.getvalue())


# --- validation ------------------------------------------------------------------------------------------

def test_validate_exports_passes_for_good_files(draft):
    report = validate_exports(draft, build_pdf(draft), build_docx(draft))
    failed = [c for g in ("content", "pdf", "docx", "cross") for c in report[g]["checks"] if not c["ok"]]
    assert report["ok"], failed
    assert report["pdf"]["pages"] == 1


def test_validate_detects_content_mismatch(draft):
    other = dict(draft, name="Someone Else", summary="Completely different summary.")
    report = validate_exports(draft, build_pdf(other), build_docx(other))
    assert not report["ok"]
    assert not report["pdf"]["ok"] and not report["docx"]["ok"]


def test_validate_detects_pdf_docx_difference(draft):
    other = dict(draft, summary=draft["summary"] + " Extra sentence.")
    report = validate_exports(draft, build_pdf(draft), build_docx(other))
    assert not report["cross"]["ok"]


def test_validate_handles_garbage_files(draft):
    report = validate_exports(draft, b"not a pdf", b"not a docx")
    assert not report["ok"]
    assert not report["pdf"]["ok"] and not report["docx"]["ok"]


def test_missing_name_and_contact_fail_content_checks(draft):
    draft.update(name="", email="", phone="")
    report = validate_exports(draft, build_pdf(draft), build_docx(draft))
    labels = {c["label"] for c in report["content"]["checks"] if not c["ok"]}
    assert {"Candidate name present", "Contact details present in the document body"} <= labels
    assert not report["ok"]


def test_long_resume_stays_within_two_pages_or_is_flagged(draft):
    draft["experience"][0]["bullets"] = [f"Delivered improvement number {i} for the platform" for i in range(24)]
    assert validate_exports(draft, build_pdf(draft), build_docx(draft))["pdf"]["pages"] <= 2
    draft["experience"][0]["bullets"] = [f"Delivered improvement number {i} for the platform" for i in range(140)]
    report = validate_exports(draft, build_pdf(draft), build_docx(draft))
    assert not report["ok"] and report["pdf"]["pages"] > 2


def test_empty_resume_builds_without_crashing():
    resume = empty_resume()
    assert build_pdf(resume).startswith(b"%PDF-")
    assert build_docx(resume)[:2] == b"PK"


# --- editor round trip & validation ------------------------------------------------------------------------

def test_form_round_trip_preserves_resume(draft):
    rebuilt, errors = form_to_resume(resume_to_form(draft))
    assert errors == {}
    assert rebuilt == draft


def test_form_round_trip_keeps_parenthesised_skill_lists():
    resume = empty_resume()
    resume.update(name="Jane Doe", skills=[{"category": "Databases", "items": ["SQL (PostgreSQL, MySQL)", "Redis"]}])
    rebuilt, errors = form_to_resume(resume_to_form(resume))
    assert errors == {} and rebuilt["skills"] == resume["skills"]


@pytest.mark.parametrize("field,value,fragment", [
    ("name", "   ", "enter your name"),
    ("email", "not-an-email", "valid email"),
    ("links", "has spaces.com", "without spaces"),
    ("links", "\n".join(f"site{i}.com" for i in range(9)), "At most"),
    ("summary", "x" * 1600, "Too long"),
    ("projects", "\n\n".join(f"P{i}\n- b" for i in range(14)), "At most"),
    ("experience", "Role\n- " + "y" * 450, "too long"),
])
def test_form_validation_errors(draft, field, value, fragment):
    form = resume_to_form(draft)
    form[field] = value
    _, errors = form_to_resume(form)
    assert fragment in errors[field]


def test_form_strips_control_characters(draft):
    form = resume_to_form(draft)
    form["summary"] = "Hello\x00 world\x07"
    resume, errors = form_to_resume(form)
    assert errors == {} and resume["summary"] == "Hello world"


# --- context store --------------------------------------------------------------------------------------------

def test_context_store_expires_and_evicts():
    now = [0.0]
    store = ContextStore(ttl_seconds=10, max_items=2, clock=lambda: now[0])
    a = store.put({"v": 1})
    assert store.get(a) == {"v": 1}
    now[0] = 11
    assert store.get(a) is None                      # expired
    b, c, d = store.put({"v": 2}), store.put({"v": 3}), store.put({"v": 4})
    assert store.get(b) is None and store.get(c) and store.get(d)   # oldest evicted at capacity
    store.delete(c)
    assert store.get(c) is None


def test_context_store_sliding_expiry():
    now = [0.0]
    store = ContextStore(ttl_seconds=10, clock=lambda: now[0])
    token = store.put({"v": 1})
    now[0] = 8
    assert store.get(token)                          # refreshed
    now[0] = 16
    assert store.get(token)                          # still alive: 8 s since last access
    now[0] = 30
    assert store.get(token) is None
