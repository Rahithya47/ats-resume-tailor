import io
import re

import pytest
from docx import Document

from app.services.export_validation import docx_text_of, pdf_text_of
from tests.conftest import SAMPLE_JD, SAMPLE_LINES


def _token(html: str) -> str:
    return re.search(r'name="ctx" value="([^"]+)"', html).group(1)


def _article(html: str) -> str:
    return re.search(r"<article.*?</article>", html, re.S).group(0)


@pytest.fixture
def analyzed(post_analysis, make_docx):
    """Run an analysis; return (token, results page html)."""
    def _run(lines=SAMPLE_LINES, jd=SAMPLE_JD):
        html = post_analysis(make_docx(lines), jd=jd, title="Backend Developer").get_data(as_text=True)
        return _token(html), html
    return _run


@pytest.fixture
def generated(client, analyzed):
    token, _ = analyzed()
    client.post("/resume/generate", data={"ctx": token})
    return token


def _follow_flash(client, response):
    return client.get(response.headers["Location"]).get_data(as_text=True)


# --- results page -----------------------------------------------------------------------------------------

def test_results_page_offers_generation_with_unconfirmed_skills(analyzed):
    token, html = analyzed()
    assert "Generate Tailored Resume" in html
    assert 'name="confirm_skill" value="Docker"' in html and "checked" not in html.split('value="Docker"')[1][:30]
    assert "genuinely have it" in html


def test_existing_analysis_and_history_still_work(client, generated):
    page = client.get("/history").get_data(as_text=True)
    assert "Backend Developer" in page
    detail = client.get("/history/1").get_data(as_text=True)
    assert "Estimated keyword match" in detail and "Generate Tailored Resume" not in detail


def test_back_to_analysis_results_keeps_analysis(client, generated):
    html = client.get(f"/analysis/{generated}").get_data(as_text=True)
    assert "Estimated keyword match" in html and "Open current draft" in html
    assert "Python" in html                     # evidence still available while the session lives


# --- generate / preview ---------------------------------------------------------------------------------------

def test_generate_redirects_and_preview_shows_tailored_resume(client, analyzed):
    token, _ = analyzed()
    response = client.post("/resume/generate", data={"ctx": token})
    assert response.status_code == 302 and response.headers["Location"].endswith(f"/resume/{token}/preview")
    html = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Your tailored resume is ready" in html
    assert "Please verify before you apply" in html
    assert "not an official ATS score" in html
    assert "Download ATS Resume (PDF)" in html and "Download ATS Resume (DOCX)" in html
    resume = _article(html)
    assert "Rahithya K" in resume and "Python, SQL, JavaScript" in resume
    assert "Docker" not in resume and "Kubernetes" not in resume
    assert "Required skills: missing (1)" in html            # keyword coverage report is transparent
    assert "Preferred skills: matched (2)" in html


def test_confirmed_skills_are_added_only_when_ticked_and_valid(client, analyzed):
    token, _ = analyzed()
    client.post("/resume/generate", data={"ctx": token, "confirm_skill": ["Docker", "Redis", "<b>x</b>"]})
    resume = _article(client.get(f"/resume/{token}/preview").get_data(as_text=True))
    assert "Additional Skills:</strong> Docker" in resume
    assert "Redis" not in resume and "&lt;b&gt;" not in resume


def test_preview_before_generate_is_blocked(client, analyzed):
    token, _ = analyzed()
    response = client.get(f"/resume/{token}/preview")
    assert response.status_code == 302 and f"/analysis/{token}" in response.headers["Location"]
    assert "Generate your tailored resume first" in _follow_flash(client, response)


# --- edit & save ------------------------------------------------------------------------------------------------

def test_edit_save_updates_preview_and_exports(client, generated):
    page = client.get(f"/resume/{generated}/preview").get_data(as_text=True)
    assert 'id="edit-form"' in page and 'name="summary"' in page
    form = {
        "name": "Rahithya K", "headline": "", "email": "rahithya@example.com", "phone": "+91 98765 43210",
        "location": "Hyderabad, India", "links": "github.com/rahithya",
        "summary": "Edited summary written by me.", "skills": "Languages: Python, SQL",
        "projects": "Expense Tracker | Flask\n- Built a REST API", "experience": "", "education": "B.Tech, XYZ | 2021 - 2025",
        "certifications": "", "additional": "",
    }
    response = client.post(f"/resume/{generated}/save", data=form)
    assert response.status_code == 302
    assert "Changes saved" in _follow_flash(client, response)
    assert "Edited summary written by me." in _article(client.get(f"/resume/{generated}/preview").get_data(as_text=True))
    pdf = client.get(f"/resume/{generated}/download/pdf").data
    docx = client.get(f"/resume/{generated}/download/docx").data
    assert "Edited summary written by me." in pdf_text_of(pdf) and "Edited summary written by me." in docx_text_of(docx)
    assert "Experience" not in pdf_text_of(pdf)               # emptied sections disappear from both files


def test_invalid_edit_is_rejected_and_not_saved(client, generated):
    before = client.get(f"/resume/{generated}/preview").get_data(as_text=True)
    response = client.post(f"/resume/{generated}/save", data={"name": "", "email": "bad", "summary": "x" * 2000})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "Please enter your name." in html and "valid email" in html and "Too long" in html
    assert "Your changes were not saved" in html
    assert _article(client.get(f"/resume/{generated}/preview").get_data(as_text=True)) == _article(before)


def test_user_text_is_escaped_in_page_pdf_and_docx(client, generated):
    form = {"name": "Jane <i>Doe</i>", "email": "jane@example.com", "summary": "<script>alert(1)</script> & R&D"}
    client.post(f"/resume/{generated}/save", data=form)
    page = client.get(f"/resume/{generated}/preview").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    assert "<script>alert(1)</script> & R&D" in pdf_text_of(client.get(f"/resume/{generated}/download/pdf").data)
    assert "<script>alert(1)</script> & R&D" in docx_text_of(client.get(f"/resume/{generated}/download/docx").data)


# --- downloads ---------------------------------------------------------------------------------------------------

def test_download_pdf_end_to_end(client, generated):
    response = client.get(f"/resume/{generated}/download/pdf")
    assert response.status_code == 200 and response.mimetype == "application/pdf"
    assert 'filename=Rahithya_K_Tailored_Resume.pdf' in response.headers["Content-Disposition"]
    assert response.headers["Cache-Control"] == "no-store"
    assert response.data.startswith(b"%PDF-")
    text = pdf_text_of(response.data)
    assert "Rahithya K" in text and "rahithya@example.com" in text and "Professional Summary" in text
    assert "Docker" not in text


def test_download_docx_end_to_end(client, generated):
    response = client.get(f"/resume/{generated}/download/docx")
    assert response.status_code == 200
    assert response.mimetype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert 'filename=Rahithya_K_Tailored_Resume.docx' in response.headers["Content-Disposition"]
    doc = Document(io.BytesIO(response.data))
    assert doc.tables == []
    assert "Python, SQL, JavaScript" in "\n".join(p.text for p in doc.paragraphs)


def test_pdf_and_docx_contain_the_same_approved_content(client, generated):
    pdf = pdf_text_of(client.get(f"/resume/{generated}/download/pdf").data)
    docx = docx_text_of(client.get(f"/resume/{generated}/download/docx").data)
    norm = lambda t: re.sub(r"[^\w\s]", " ", t.replace("•", " ")).split()  # noqa: E731
    assert norm(pdf) == norm(docx)


def test_download_before_generation_is_blocked(client, analyzed):
    token, _ = analyzed()
    for fmt in ("pdf", "docx"):
        response = client.get(f"/resume/{token}/download/{fmt}")
        assert response.status_code == 302 and response.mimetype != "application/pdf"
        assert "Generate your tailored resume first" in _follow_flash(client, response)


def test_download_blocked_when_validation_fails_then_allowed_after_fix(client, analyzed):
    lines = ["rahithya@example.com", "", "Technical Skills", "Python, Flask"]
    token, _ = analyzed(lines=lines, jd="Requirements:\nPython, Flask")
    client.post("/resume/generate", data={"ctx": token})        # name could not be detected
    page = client.get(f"/resume/{token}/preview").get_data(as_text=True)
    assert "couldn&#39;t detect your name" in page and "Downloads are unavailable" in page
    assert "Candidate name present" in page and "needs attention" in page
    response = client.get(f"/resume/{token}/download/pdf")
    assert response.status_code == 302
    assert "did not pass validation" in _follow_flash(client, response)
    form = {"name": "Jane Doe", "email": "rahithya@example.com", "skills": "Python, Flask"}
    client.post(f"/resume/{token}/save", data=form)
    assert client.get(f"/resume/{token}/download/pdf").status_code == 200
    assert client.get(f"/resume/{token}/download/docx").status_code == 200


# --- invalid requests & errors ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("post", "/resume/generate"), ("get", "/resume/nope/preview"), ("post", "/resume/nope/save"),
    ("get", "/resume/nope/download/pdf"), ("get", "/resume/nope/download/docx"), ("post", "/resume/nope/discard"),
    ("get", "/analysis/nope"),
])
def test_unknown_token_redirects_with_message(client, method, path):
    response = getattr(client, method)(path, data={"ctx": "nope"} if method == "post" else None)
    assert response.status_code == 302 and response.headers["Location"].endswith("/analyze")
    assert "expired" in _follow_flash(client, response)


def test_other_browser_session_cannot_access_a_draft(app, generated):
    stranger = app.test_client()
    for path in (f"/resume/{generated}/preview", f"/resume/{generated}/download/pdf", f"/analysis/{generated}"):
        assert stranger.get(path).status_code == 302
    assert stranger.post("/resume/generate", data={"ctx": generated}).status_code == 302


def test_unknown_download_format_is_404(client, generated):
    assert client.get(f"/resume/{generated}/download/exe").status_code == 404


def test_generation_without_recognizable_sections_shows_message(client, analyzed):
    token, _ = analyzed(lines=["Just some free text about me with no headings at all."])
    response = client.post("/resume/generate", data={"ctx": token})
    assert response.status_code == 302 and f"/analysis/{token}" in response.headers["Location"]
    assert "recognizable resume sections" in _follow_flash(client, response)


def test_unexpected_generation_error_does_not_leak_details(client, analyzed, monkeypatch):
    token, _ = analyzed()

    def boom(*args, **kwargs):
        raise RuntimeError("secret /home/user/key.pem traceback")

    monkeypatch.setattr("app.resume_routes.generate_tailored_resume", boom)
    response = client.post("/resume/generate", data={"ctx": token})
    page = _follow_flash(client, response)
    assert "couldn&#39;t generate your tailored resume" in page
    assert "secret" not in page and "key.pem" not in page and "Traceback" not in page
    assert "Estimated keyword match" in page                       # analysis is unchanged
    monkeypatch.undo()
    assert client.post("/resume/generate", data={"ctx": token}).status_code == 302   # can retry


def test_unexpected_export_error_does_not_leak_details(client, generated, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret /var/tmp/leak")

    monkeypatch.setattr("app.resume_routes.build_pdf", boom)
    response = client.get(f"/resume/{generated}/download/pdf")
    assert response.status_code == 302
    page = _follow_flash(client, response)
    assert "couldn&#39;t create the file" in page and "secret" not in page and "/var/tmp" not in page
    preview = client.get(f"/resume/{generated}/preview").get_data(as_text=True)   # page still renders
    assert "could not run" in preview and "secret" not in preview


def test_discard_removes_draft_from_memory(app, client, generated):
    response = client.post(f"/resume/{generated}/discard")
    assert response.status_code == 302 and response.headers["Location"].endswith("/")
    assert len(app.extensions["context_store"]) == 0
    assert client.get(f"/resume/{generated}/preview").status_code == 302
    assert client.get("/history/1").status_code == 200                  # saved history untouched


def test_resume_text_never_written_to_database(app, client, generated):
    import sqlite3

    conn = sqlite3.connect(app.config["DATABASE"])
    dump = "\n".join(conn.iterdump())
    conn.close()
    assert "Rahithya" not in dump and "rahithya@example.com" not in dump and "Expense Tracker" not in dump


def test_expired_context_redirects(app, client, generated):
    store = app.extensions["context_store"]
    store._items.clear()                                           # simulate TTL expiry
    assert client.get(f"/resume/{generated}/preview").status_code == 302


# --- CSRF (needs the real Flask-WTF) ----------------------------------------------------------------------------------

def test_csrf_required_for_all_new_post_routes(csrf_app):
    client = csrf_app.test_client()
    for path in ("/resume/generate", "/resume/abc/save", "/resume/abc/discard"):
        assert client.post(path, data={"ctx": "abc"}).status_code == 400
