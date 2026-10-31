import io
import zipfile

import pytest
from werkzeug.datastructures import FileStorage

from app.validators import (
    InputError,
    check_file_size,
    check_signature,
    validate_job_description,
    validate_optional_field,
    validate_upload,
)


def _file(name):
    return FileStorage(stream=io.BytesIO(b"x"), filename=name)


def test_accepts_pdf_and_docx_case_insensitive():
    assert validate_upload(_file("CV.PDF")) == ".pdf"
    assert validate_upload(_file("cv.docx")) == ".docx"


@pytest.mark.parametrize("name", ["cv.txt", "cv.doc", "cv.exe", "cv", "cv.pdf.exe"])
def test_rejects_bad_extensions(name):
    with pytest.raises(InputError):
        validate_upload(_file(name))


def test_rejects_missing_file():
    with pytest.raises(InputError):
        validate_upload(None)
    with pytest.raises(InputError):
        validate_upload(_file(""))


def test_size_checks(tmp_path):
    empty = tmp_path / "e.pdf"
    empty.write_bytes(b"")
    with pytest.raises(InputError, match="empty"):
        check_file_size(str(empty), 100)
    big = tmp_path / "b.pdf"
    big.write_bytes(b"x" * 200)
    with pytest.raises(InputError, match="too large"):
        check_file_size(str(big), 100)
    check_file_size(str(big), 1000)


def test_pdf_signature(tmp_path):
    good = tmp_path / "g.pdf"
    good.write_bytes(b"%PDF-1.7\n...")
    check_signature(str(good), ".pdf")
    bad = tmp_path / "b.pdf"
    bad.write_bytes(b"MZ not a pdf")
    with pytest.raises(InputError):
        check_signature(str(bad), ".pdf")


def test_docx_signature(tmp_path):
    bad = tmp_path / "b.docx"
    bad.write_bytes(b"not a zip")
    with pytest.raises(InputError):
        check_signature(str(bad), ".docx")
    wrong_zip = tmp_path / "w.docx"
    with zipfile.ZipFile(wrong_zip, "w") as z:
        z.writestr("hello.txt", "hi")
    with pytest.raises(InputError):
        check_signature(str(wrong_zip), ".docx")


def test_job_description_validation():
    with pytest.raises(InputError):
        validate_job_description("   ", 20, 100)
    with pytest.raises(InputError, match="too short"):
        validate_job_description("Python", 20, 100)
    with pytest.raises(InputError, match="too long"):
        validate_job_description("x" * 101, 20, 100)
    assert validate_job_description("  Python and Flask developer needed  ", 20, 100).startswith("Python")


def test_optional_field():
    assert validate_optional_field("  Dev \n Ops  ", "Title", 20) == "Dev Ops"
    assert validate_optional_field("", "Title", 20) == ""
    with pytest.raises(InputError):
        validate_optional_field("x" * 21, "Title", 20)
