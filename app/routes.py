"""Flask routes. Business logic lives in app.services; SQL lives in app.database."""
from __future__ import annotations

import os
import tempfile

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from app import database as db
from app.context_store import create_context, get_context
from app.services.analysis import run_analysis
from app.services.resume_parser import extract_resume_text
from app.validators import (
    InputError,
    check_file_size,
    check_signature,
    validate_job_description,
    validate_optional_field,
    validate_upload,
)

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    recent = db.list_analyses(limit=5)
    return render_template(
        "index.html",
        total=db.count_analyses(),
        recent=recent,
        latest=recent[0] if recent else None,
    )


@bp.get("/analyze")
def analyze_form():
    return render_template("analyze.html", form={}, errors={}, max_mb=current_app.config["MAX_UPLOAD_MB"])


def _read_resume(upload, ext: str) -> str:
    """Save the upload to a random temp file, extract its text, always delete the file."""
    max_bytes = int(current_app.config["MAX_CONTENT_LENGTH"])
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=ext, dir=current_app.config.get("UPLOAD_TMP_DIR"))
        os.close(fd)
        upload.save(tmp_path)
        check_file_size(tmp_path, max_bytes)
        check_signature(tmp_path, ext)
        return extract_resume_text(tmp_path, ext)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                current_app.logger.warning("Could not delete temporary upload file")


@bp.post("/analyze")
def analyze_submit():
    cfg = current_app.config
    form = {
        "job_title": request.form.get("job_title", ""),
        "company_name": request.form.get("company_name", ""),
        "job_description": request.form.get("job_description", ""),
    }
    errors: dict[str, str] = {}
    cleaned: dict[str, str] = {}

    for key, label in (("job_title", "Job title"), ("company_name", "Company")):
        try:
            cleaned[key] = validate_optional_field(form[key], label, cfg["MAX_FIELD_CHARS"])
        except InputError as exc:
            errors[key] = str(exc)
    try:
        cleaned["job_description"] = validate_job_description(
            form["job_description"], cfg["MIN_JOB_DESCRIPTION_CHARS"], cfg["MAX_JOB_DESCRIPTION_CHARS"]
        )
    except InputError as exc:
        errors["job_description"] = str(exc)

    upload = request.files.get("resume")
    ext = ""
    try:
        ext = validate_upload(upload)
    except InputError as exc:
        errors["resume"] = str(exc)

    resume_text = ""
    if not errors:
        try:
            resume_text = _read_resume(upload, ext)
        except InputError as exc:
            errors["resume"] = str(exc)

    if errors:
        return render_template("analyze.html", form=form, errors=errors, max_mb=cfg["MAX_UPLOAD_MB"]), 400

    result = run_analysis(resume_text, cleaned["job_description"])
    analysis_id = db.insert_analysis(cleaned["job_title"], cleaned["company_name"], result)
    analysis = {
        **result,
        "id": analysis_id,
        "job_title": cleaned["job_title"],
        "company_name": cleaned["company_name"],
    }
    # Rendered directly (not redirected): evidence snippets come from the resume text, which is
    # never written to the database. The text is kept in short-lived memory only (see
    # app/context_store.py) so a tailored resume can be generated from it.
    token = create_context(
        {
            "resume_text": resume_text,
            "job_description": cleaned["job_description"],
            "job_title": cleaned["job_title"],
            "company_name": cleaned["company_name"],
            "analysis": analysis,
            "draft": None,
            "notes": [],
        }
    )
    return render_template("results.html", a=analysis, ctx=token)


@bp.get("/analysis/<token>")
def analysis_view(token: str):
    """Return to the analysis results (with evidence) while the session is still alive."""
    ctx = get_context(token)
    if ctx is None:
        flash("Your session expired. Please run the analysis again.", "error")
        return redirect(url_for("main.analyze_form"))
    return render_template("results.html", a=ctx["analysis"], ctx=token, has_draft=bool(ctx.get("draft")))


@bp.get("/history")
def history():
    return render_template("history.html", analyses=db.list_analyses())


@bp.get("/history/<int:analysis_id>")
def history_detail(analysis_id: int):
    analysis = db.get_analysis(analysis_id)
    if analysis is None:
        abort(404)
    return render_template("history_detail.html", a=analysis)


@bp.post("/history/<int:analysis_id>/delete")
def delete_one(analysis_id: int):
    if db.delete_analysis(analysis_id):
        flash("Analysis deleted.", "success")
    else:
        abort(404)
    return redirect(url_for("main.history"))


@bp.post("/history/delete-all")
def delete_all():
    if request.form.get("confirm") != "yes":
        flash("Please tick the confirmation box to delete all history.", "error")
        return redirect(url_for("main.history"))
    count = db.delete_all_analyses()
    flash(f"Deleted {count} analysis record{'s' if count != 1 else ''}.", "success")
    return redirect(url_for("main.history"))
