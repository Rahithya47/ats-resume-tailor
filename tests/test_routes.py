import io
import os
import re

from tests.conftest import JD, RESUME_LINES


def test_pages_load(client):
    for path in ("/", "/analyze", "/history"):
        assert client.get(path).status_code == 200


def test_404_page(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert b"Page not found" in response.data


def test_successful_docx_analysis(post_analysis, make_docx, tmp_upload_dir):
    response = post_analysis(make_docx(RESUME_LINES))
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Estimated keyword match" in body
    assert "not an official ATS score" in body
    assert "64%" in body  # 4/5 required (80%) * 0.8 + 0/1 preferred * 0.2
    assert "Docker" in body and "Kubernetes" in body
    assert "jane.doe@example.com" not in body  # contact details never echoed
    assert os.listdir(tmp_upload_dir) == []  # temp file cleaned up


def test_successful_pdf_analysis(post_analysis, make_pdf):
    response = post_analysis(make_pdf("Skills: Python, Flask, SQL, Docker"), filename="cv.pdf")
    assert response.status_code == 200
    assert "Estimated keyword match" in response.get_data(as_text=True)


def test_results_change_with_resume(post_analysis, make_docx):
    strong = post_analysis(make_docx(["Python Flask SQL Docker REST APIs Kubernetes"])).get_data(as_text=True)
    weak = post_analysis(make_docx(["I enjoy gardening"])).get_data(as_text=True)
    assert "100%" in strong
    assert "0%" in weak


def test_invalid_extension(post_analysis):
    response = post_analysis(b"hello", filename="cv.txt")
    assert response.status_code == 400
    assert b"Unsupported file type" in response.data


def test_missing_file(post_analysis):
    response = post_analysis(None)
    assert response.status_code == 400
    assert b"choose a resume file" in response.data


def test_empty_job_description(post_analysis, make_docx):
    response = post_analysis(make_docx(RESUME_LINES), jd="   ")
    assert response.status_code == 400
    assert b"paste the job description" in response.data


def test_oversized_file(post_analysis):
    response = post_analysis(b"x" * (2 * 1024 * 1024), filename="big.pdf")
    assert response.status_code == 413
    assert b"too large" in response.data


def test_fake_pdf_and_cleanup(post_analysis, tmp_upload_dir):
    response = post_analysis(b"this is not a pdf", filename="cv.pdf")
    assert response.status_code == 400
    assert b"valid PDF" in response.data
    assert os.listdir(tmp_upload_dir) == []


def test_scanned_pdf_message_and_cleanup(post_analysis, make_pdf, tmp_upload_dir):
    response = post_analysis(make_pdf(""), filename="scan.pdf")
    assert response.status_code == 400
    assert b"OCR" in response.data
    assert os.listdir(tmp_upload_dir) == []


def test_form_values_kept_on_error(post_analysis):
    response = post_analysis(b"x", filename="cv.txt", title="My Title")
    assert b'value="My Title"' in response.data


def test_history_flow(client, post_analysis, make_docx):
    post_analysis(make_docx(RESUME_LINES), title="Role A")
    post_analysis(make_docx(RESUME_LINES), title="Role B")
    page = client.get("/history").get_data(as_text=True)
    assert "Role A" in page and "Role B" in page

    detail = client.get("/history/1")
    assert detail.status_code == 200
    text = detail.get_data(as_text=True)
    assert "Resume excerpts are not saved" in text
    assert "jane.doe" not in text

    assert client.post("/history/1/delete", follow_redirects=True).status_code == 200
    assert client.get("/history/1").status_code == 404
    assert client.post("/history/1/delete").status_code == 404


def test_delete_all_requires_confirmation(client, post_analysis, make_docx):
    post_analysis(make_docx(RESUME_LINES))
    client.post("/history/delete-all")
    assert "Untitled" not in client.get("/history").get_data(as_text=True)  # still has the row
    assert client.get("/history/1").status_code == 200
    client.post("/history/delete-all", data={"confirm": "yes"})
    assert client.get("/history/1").status_code == 404


def test_xss_is_escaped(post_analysis, make_docx):
    payload = "<script>alert(1)</script>"
    body = post_analysis(make_docx(RESUME_LINES), title=payload, company=payload).get_data(as_text=True)
    assert payload not in body
    assert "&lt;script&gt;" in body


def test_sql_injection_is_inert(client, post_analysis, make_docx):
    post_analysis(make_docx(RESUME_LINES), title="'; DROP TABLE analyses;--")
    page = client.get("/history").get_data(as_text=True)
    assert "DROP TABLE" in page  # stored as plain text, table still works
    assert client.get("/history/1").status_code == 200


def test_no_resume_text_stored(app, post_analysis, make_docx):
    post_analysis(make_docx(["Secret Employer Corp wrote Python code. jane.doe@example.com"]), jd="Requirements:\nPython and SQL developer")
    import sqlite3

    conn = sqlite3.connect(app.config["DATABASE"])
    dump = "\n".join(conn.iterdump())
    conn.close()
    assert "Secret Employer" not in dump
    assert "jane.doe" not in dump


def test_csrf_enforced(csrf_app):
    client = csrf_app.test_client()
    assert client.post("/history/delete-all", data={"confirm": "yes"}).status_code == 400
    assert client.post("/history/1/delete").status_code == 400
    response = client.post("/analyze", data={"job_description": JD})
    assert response.status_code == 400


def test_csrf_token_accepted(csrf_app):
    client = csrf_app.test_client()
    html = client.get("/history").get_data(as_text=True)
    # History is empty, so use the analyze page to obtain a token.
    html = client.get("/analyze").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    response = client.post(
        "/history/delete-all", data={"confirm": "yes", "csrf_token": token}, follow_redirects=True
    )
    assert response.status_code == 200
