import io

import pytest

from app import create_app

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from docx import Document

JD = """Senior Backend Developer

Requirements:
- Python, Flask and SQL
- Docker
- REST APIs

Nice to have:
- Kubernetes
"""

RESUME_LINES = [
    "Jane Doe",
    "jane.doe@example.com  +1 555 123 4567",
    "Skills: Python, Flask, SQL",
    "Built REST APIs for an internal tool.",
]


SAMPLE_RESUME = """Rahithya K
Hyderabad, India | rahithya@example.com | +91 98765 43210
linkedin.com/in/rahithya | github.com/rahithya

Summary
Computer science student who builds web applications.

Technical Skills
Languages: JS, Python, SQL
Frameworks: Flask, React
Tools: Git, Postgres

Projects
Expense Tracker | Flask, SQLite
- Built a REST API with Flask and SQLite to track expenses
- Wrote unit tests with pytest covering core routes
Portfolio Website | HTML, CSS, JS
- Designed a responsive personal site

Experience
Software Intern | Acme Corp | June 2024 – August 2024
- Fixed bugs in a Python service
- Wrote SQL queries for reporting

Education
B.Tech in Computer Science, XYZ University | 2021 – 2025
CGPA: 8.5

Certifications
Python for Everybody (Coursera)
"""
SAMPLE_LINES = SAMPLE_RESUME.split("\n")
SAMPLE_JD = (
    "Requirements:\n- Python, Flask, SQL, Docker\n- REST APIs, Git\n"
    "Nice to have:\n- Kubernetes, PostgreSQL, JavaScript\n"
)


@pytest.fixture
def tmp_upload_dir(tmp_path):
    path = tmp_path / "uploads_tmp"
    path.mkdir()
    return path


@pytest.fixture
def app(tmp_path, tmp_upload_dir):
    return create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.db"),
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test-secret",
            "UPLOAD_TMP_DIR": str(tmp_upload_dir),
            "MAX_UPLOAD_MB": 1,
        }
    )


@pytest.fixture
def csrf_app(tmp_path, tmp_upload_dir):
    return create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "csrf.db"),
            "WTF_CSRF_ENABLED": True,
            "SECRET_KEY": "test-secret",
            "UPLOAD_TMP_DIR": str(tmp_upload_dir),
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_docx():
    def _make(lines=None, table_rows=None) -> bytes:
        doc = Document()
        for line in lines or []:
            doc.add_paragraph(line)
        if table_rows:
            table = doc.add_table(rows=len(table_rows), cols=len(table_rows[0]))
            for r, row in enumerate(table_rows):
                for c, value in enumerate(row):
                    table.cell(r, c).text = value
        buffer = io.BytesIO()
        doc.save(buffer)
        return buffer.getvalue()

    return _make


@pytest.fixture
def make_pdf():
    def _make(text: str | None = "", encrypt: bool = False) -> bytes:
        doc = fitz.open()
        page = doc.new_page()
        if text:
            y = 72
            for line in text.split("\n"):
                page.insert_text((72, y), line)
                y += 18
        kwargs = {}
        if encrypt:
            kwargs = {"encryption": fitz.PDF_ENCRYPT_AES_256, "user_pw": "secret", "owner_pw": "owner"}
        data = doc.tobytes(**kwargs)
        doc.close()
        return data

    return _make


@pytest.fixture
def post_analysis(client):
    def _post(file_bytes=None, filename="resume.docx", jd=JD, title="Backend Dev", company="Acme"):
        data = {"job_title": title, "company_name": company, "job_description": jd}
        if file_bytes is not None:
            data["resume"] = (io.BytesIO(file_bytes), filename)
        return client.post("/analyze", data=data, content_type="multipart/form-data")

    return _post
