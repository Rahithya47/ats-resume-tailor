import pytest

from app.services.resume_parser import ResumeParseError, extract_resume_text


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def test_docx_paragraphs_and_tables(tmp_path, make_docx):
    data = make_docx(["Skills: Python"], table_rows=[["Docker", "AWS"]])
    text = extract_resume_text(_write(tmp_path, "a.docx", data), ".docx")
    assert "Python" in text and "Docker" in text and "AWS" in text


def test_pdf_text(tmp_path, make_pdf):
    path = _write(tmp_path, "a.pdf", make_pdf("Skills: Python and Flask"))
    assert "Python" in extract_resume_text(path, ".pdf")


def test_scanned_pdf_mentions_ocr(tmp_path, make_pdf):
    path = _write(tmp_path, "scan.pdf", make_pdf(""))
    with pytest.raises(ResumeParseError, match="OCR"):
        extract_resume_text(path, ".pdf")


def test_encrypted_pdf(tmp_path, make_pdf):
    path = _write(tmp_path, "enc.pdf", make_pdf("secret text", encrypt=True))
    with pytest.raises(ResumeParseError, match="password"):
        extract_resume_text(path, ".pdf")


def test_corrupted_files(tmp_path):
    with pytest.raises(ResumeParseError):
        extract_resume_text(_write(tmp_path, "bad.pdf", b"%PDF-1.4 garbage"), ".pdf")
    with pytest.raises(ResumeParseError):
        extract_resume_text(_write(tmp_path, "bad.docx", b"garbage"), ".docx")


def test_empty_docx(tmp_path, make_docx):
    with pytest.raises(ResumeParseError, match="No text"):
        extract_resume_text(_write(tmp_path, "e.docx", make_docx([])), ".docx")


def test_unsupported_extension(tmp_path):
    with pytest.raises(ResumeParseError):
        extract_resume_text(_write(tmp_path, "a.txt", b"hi"), ".txt")
