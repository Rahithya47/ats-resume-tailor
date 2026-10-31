"""Routes for generating, previewing, editing and downloading the tailored resume."""
from __future__ import annotations

import io
from typing import Any

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for

from app.context_store import discard_context, get_context
from app.services.export_validation import validate_exports
from app.services.keyword_extractor import compare_terms, extract_job_terms
from app.services.resume_edit import form_to_resume, resume_to_form
from app.services.resume_export import build_blocks, build_docx, build_pdf, plain_text, safe_filename
from app.services.scoring import calculate_score
from app.services.tailoring import GenerationError, generate_tailored_resume

bp = Blueprint("resume", __name__, url_prefix="/resume")

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_CONFIRMED_SKILLS = 20


def _expired():
    flash("Your session expired or this resume draft was not found. Please run the analysis again.", "error")
    return redirect(url_for("main.analyze_form"))


def _need_draft(token: str):
    flash("Generate your tailored resume first.", "error")
    return redirect(url_for("main.analysis_view", token=token))


def _coverage(draft: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """Keyword coverage of the tailored resume, using the same method and formula as the analysis."""
    terms = extract_job_terms(ctx["job_description"])
    result = compare_terms(plain_text(draft), terms["required"], terms["preferred"])
    pick = lambda items, level: [i["term"] for i in items if i["level"] == level]  # noqa: E731
    matched_req, matched_pref = pick(result["matched"], "required"), pick(result["matched"], "preferred")
    breakdown = calculate_score(len(terms["required"]), len(matched_req), len(terms["preferred"]), len(matched_pref))
    return {
        "matched_required": matched_req,
        "missing_required": pick(result["missing"], "required"),
        "matched_preferred": matched_pref,
        "missing_preferred": pick(result["missing"], "preferred"),
        "score": breakdown["overall"],
        "breakdown": breakdown,
        "original_score": ctx["analysis"].get("match_score"),
    }


def _build_exports(draft: dict[str, Any]) -> tuple[bytes, bytes, dict[str, Any]]:
    pdf, docx = build_pdf(draft), build_docx(draft)
    return pdf, docx, validate_exports(draft, pdf, docx)


def _render_preview(token: str, ctx: dict[str, Any], form=None, errors=None, status: int = 200):
    draft = ctx["draft"]
    try:
        report: dict[str, Any] | None = _build_exports(draft)[2]
    except Exception:
        current_app.logger.exception("Export validation could not run")
        report = None
    html = render_template(
        "resume_preview.html",
        token=token,
        blocks=build_blocks(draft),
        form=form if form is not None else resume_to_form(draft),
        errors=errors or {},
        report=report,
        coverage=_coverage(draft, ctx),
        notes=ctx.get("notes", []),
        job_title=ctx.get("job_title", ""),
    )
    return html, status


@bp.post("/generate")
def generate():
    token = request.form.get("ctx", "")
    ctx = get_context(token)
    if ctx is None:
        return _expired()
    allowed = {m["term"] for m in ctx["analysis"]["missing"]}
    confirmed = [s for s in request.form.getlist("confirm_skill") if s in allowed][:MAX_CONFIRMED_SKILLS]
    try:
        draft, notes = generate_tailored_resume(
            ctx["resume_text"], ctx["job_description"], ctx.get("job_title", ""), confirmed
        )
    except GenerationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.analysis_view", token=token))
    except Exception:
        current_app.logger.exception("Resume generation failed")
        flash("We couldn't generate your tailored resume. Your analysis is unchanged. Please try again.", "error")
        return redirect(url_for("main.analysis_view", token=token))
    ctx["draft"], ctx["notes"] = draft, notes
    flash("Your tailored resume is ready. Review and edit it below before downloading.", "success")
    return redirect(url_for("resume.preview", token=token))


@bp.get("/<token>/preview")
def preview(token: str):
    ctx = get_context(token)
    if ctx is None:
        return _expired()
    if not ctx.get("draft"):
        return _need_draft(token)
    return _render_preview(token, ctx)


@bp.post("/<token>/save")
def save(token: str):
    ctx = get_context(token)
    if ctx is None:
        return _expired()
    if not ctx.get("draft"):
        return _need_draft(token)
    resume, errors = form_to_resume(request.form)
    if errors:
        flash("Some fields need attention. Your changes were not saved.", "error")
        return _render_preview(token, ctx, form=dict(request.form), errors=errors, status=400)
    ctx["draft"] = resume
    flash("Changes saved. Downloads use this saved version.", "success")
    return redirect(url_for("resume.preview", token=token))


def _download(token: str, fmt: str):
    ctx = get_context(token)
    if ctx is None:
        return _expired()
    draft = ctx.get("draft")
    if not draft:
        return _need_draft(token)
    try:
        pdf, docx, report = _build_exports(draft)
    except Exception:
        current_app.logger.exception("Resume export failed")
        flash("We couldn't create the file. Your draft is unchanged. Please try again.", "error")
        return redirect(url_for("resume.preview", token=token))
    if not report["ok"]:
        flash("The exported files did not pass validation, so no file was downloaded. "
              "See the export checks below.", "error")
        return redirect(url_for("resume.preview", token=token))
    data, mime = (pdf, PDF_MIME) if fmt == "pdf" else (docx, DOCX_MIME)
    response = send_file(io.BytesIO(data), mimetype=mime, as_attachment=True, download_name=safe_filename(draft, fmt))
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/<token>/download/pdf")
def download_pdf(token: str):
    return _download(token, "pdf")


@bp.get("/<token>/download/docx")
def download_docx(token: str):
    return _download(token, "docx")


@bp.post("/<token>/discard")
def discard(token: str):
    if get_context(token) is None:
        return _expired()
    discard_context(token)
    flash("Your resume data was removed from memory.", "success")
    return redirect(url_for("main.index"))
