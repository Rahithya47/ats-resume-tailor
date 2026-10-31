"""Deterministic, truthful tailoring of a parsed resume to a job description.

No AI service is used. The tailoring only:
  * reorders skills, projects, bullets and certifications by relevance to the job,
  * rewrites a short whitelist of exact synonyms to the job's wording (JS -> JavaScript),
  * builds/extends the summary from skills that are already in the resume,
  * adds skills only when the candidate explicitly confirmed them.
It never adds a skill, employer, project, metric or certification that is not in the resume.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from app.services.keyword_extractor import display_name, extract_job_terms, find_skills
from app.services.resume_structure import Resume, has_content, normalize_dates, parse_resume


class GenerationError(Exception):
    """A user-facing reason why a tailored resume could not be generated."""


# Exact synonyms only (never "related" technologies). canonical skill -> aliases rewritten to it.
SYNONYM_REWRITES: dict[str, list[str]] = {
    "javascript": ["js"],
    "postgresql": ["postgres"],
    "kubernetes": ["k8s"],
    "node.js": ["nodejs"],
    "react": ["reactjs", "react.js"],
    "vue": ["vuejs", "vue.js"],
    "aws": ["amazon web services"],
    "gcp": ["google cloud platform"],
    "ci/cd": ["ci cd"],
}
_JS_PREFIX_WORDS = {"node", "react", "vue", "next", "nuxt", "express", "angular"}


def _alias_pattern(alias: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9+#.]){re.escape(alias)}(?![A-Za-z0-9+#])", re.IGNORECASE)


def _previous_word(match: re.Match[str]) -> str:
    words = re.findall(r"[A-Za-z]+", match.string[max(0, match.start() - 12): match.start()])
    return words[-1].lower() if words else ""


def _rewrite(text: str, wanted: set[str], counts: dict[str, int]) -> str:
    for canonical, aliases in SYNONYM_REWRITES.items():
        if canonical not in wanted:
            continue
        target = display_name(canonical)
        for alias in aliases:
            def repl(match: re.Match[str], alias: str = alias, target: str = target) -> str:
                # "Node JS" / "React JS" are not the plain language "JS": leave them alone.
                if alias == "js" and _previous_word(match) in _JS_PREFIX_WORDS:
                    return match.group(0)
                if match.group(0) == target:
                    return match.group(0)
                key = f"{match.group(0)} -> {target}"
                counts[key] = counts.get(key, 0) + 1
                return target

            text = _alias_pattern(alias).sub(repl, text)
    return text


def _entry_text(entry: dict[str, Any]) -> str:
    return " ".join([entry["heading"], *entry["details"], *entry["bullets"]])


def _score(text: str, required: set[str], preferred: set[str]) -> int:
    hits = set(find_skills(text))
    return 2 * len(hits & required) + len(hits & preferred)


def _rank(item: str, required: set[str], preferred: set[str]) -> int:
    hits = set(find_skills(item))
    if hits & required:
        return 0
    if hits & preferred:
        return 1
    return 2


def resume_text(resume: Resume) -> str:
    parts = [resume["summary"]]
    for group in resume["skills"]:
        parts.append(f"{group['category']} {' '.join(group['items'])}")
    for key in ("projects", "experience", "education"):
        parts.extend(_entry_text(e) for e in resume[key])
    parts.extend(resume["certifications"])
    for extra in resume["extras"]:
        parts.extend(extra["lines"])
    return "\n".join(p for p in parts if p)


def tailor_resume(
    resume: Resume,
    required: list[str],
    preferred: list[str],
    job_title: str = "",
    confirmed_skills: list[str] | None = None,
) -> tuple[Resume, list[str]]:
    """Return (tailored copy, human-readable notes about what changed)."""
    out = copy.deepcopy(resume)
    req, pref = set(required), set(preferred)
    wanted = req | pref
    notes: list[str] = []
    rewrites: dict[str, int] = {}

    # Consistent dates everywhere.
    for key in ("projects", "experience", "education"):
        for entry in out[key]:
            entry["heading"] = normalize_dates(entry["heading"])
            entry["details"] = [normalize_dates(d) for d in entry["details"]]

    # 1. Exact-synonym wording.
    out["summary"] = _rewrite(out["summary"], wanted, rewrites)
    for group in out["skills"]:
        group["items"] = _dedupe_ci([_rewrite(i, wanted, rewrites) for i in group["items"]])
    for key in ("projects", "experience"):
        for entry in out[key]:
            entry["details"] = [_rewrite(d, wanted, rewrites) for d in entry["details"]]
            entry["bullets"] = [_rewrite(b, wanted, rewrites) for b in entry["bullets"]]
    if rewrites:
        total = sum(rewrites.values())
        examples = ", ".join(sorted(rewrites)[:3])
        notes.append(f"Reworded {total} exact synonym{'s' if total != 1 else ''} to the job's wording ({examples}).")

    # 2. Skills: job-relevant skills first, categories ordered by their best skill.
    before = [list(g["items"]) for g in out["skills"]]
    for group in out["skills"]:
        group["items"] = sorted(group["items"], key=lambda i: _rank(i, req, pref))
    out["skills"].sort(key=lambda g: min((_rank(i, req, pref) for i in g["items"]), default=2))
    if [list(g["items"]) for g in out["skills"]] != before:
        notes.append("Reordered your skills so skills the job asks for come first.")

    # 3. Confirmed skills (explicitly ticked by the candidate).
    existing = {i.casefold() for g in out["skills"] for i in g["items"]}
    added = [s for s in _dedupe_ci(list(confirmed_skills or [])) if s.casefold() not in existing]
    if added:
        out["skills"].append({"category": "Additional Skills", "items": added})
        notes.append(f"Added {len(added)} skill{'s' if len(added) != 1 else ''} you confirmed: {', '.join(added)}.")

    # 4. Projects by relevance; bullets by relevance inside projects and experience.
    original_projects = [e["heading"] for e in out["projects"]]
    out["projects"].sort(key=lambda e: -_score(_entry_text(e), req, pref))
    if [e["heading"] for e in out["projects"]] != original_projects:
        notes.append("Moved the most relevant projects to the top.")
    bullets_moved = False
    for key in ("projects", "experience"):
        for entry in out[key]:
            ordered = sorted(entry["bullets"], key=lambda b: -_score(b, req, pref))
            bullets_moved = bullets_moved or ordered != entry["bullets"]
            entry["bullets"] = ordered
    if bullets_moved:
        notes.append("Put the most relevant bullet points first within each project and role.")
    out["certifications"].sort(key=lambda c: -_score(c, req, pref))

    # 5. Summary built only from skills already present in the resume.
    present = find_skills(resume_text(out))
    top = [k for k in [*required, *preferred] if k in present][:6]
    names = [display_name(k) for k in top]
    summary = out["summary"].strip()
    if names:
        if not summary:
            who = f"{job_title} candidate" if job_title else "Candidate"
            out["summary"] = f"{who} with skills in {_join_names(names)}."
            notes.append("Wrote a short summary from skills already in your resume. Please review it.")
        elif not any(n.casefold() in summary.casefold() for n in names):
            out["summary"] = f"{summary.rstrip()} Key skills relevant to this role: {', '.join(names)}."
            notes.append("Extended your summary with matching skills from your resume.")

    # 6. Be transparent about what was NOT added.
    missing = [display_name(k) for k in [*required, *preferred] if k not in present and display_name(k) not in added]
    if missing:
        notes.append(
            "Not added because they are not in your resume: "
            + ", ".join(missing[:10])
            + ". Add them yourself in the editor only if you genuinely have them."
        )
    return out, notes


def _dedupe_ci(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for item in items:
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            out.append(item)
    return out


def _join_names(names: list[str]) -> str:
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def generate_tailored_resume(
    raw_resume_text: str, job_description: str, job_title: str = "", confirmed_skills: list[str] | None = None
) -> tuple[Resume, list[str]]:
    """Parse the uploaded resume and tailor it to the job description."""
    resume = parse_resume(raw_resume_text)
    if not has_content(resume):
        raise GenerationError(
            "We couldn't find recognizable resume sections (such as Skills, Projects or Education) "
            "in your file. Use standard section headings and try again."
        )
    terms = extract_job_terms(job_description)
    tailored, notes = tailor_resume(resume, terms["required"], terms["preferred"], job_title, confirmed_skills)
    if not tailored["name"]:
        notes.insert(0, "We couldn't detect your name. Please add it in the editor before downloading.")
    return tailored, notes
