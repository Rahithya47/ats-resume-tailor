"""Convert a resume dict to/from the plain-text fields of the editor form, with validation.

Editor formats (all plain text, one textarea per section):
  skills          one line per group:  "Languages: Python, SQL"  (or just "Python, SQL")
  projects /      blocks separated by a blank line. First line = heading, "- " lines =
  experience /    bullets, any other line before the bullets = detail (company, dates...)
  education
  certifications  one per line
  additional      "## Title" followed by one item per line
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from app.services.resume_structure import Resume, empty_resume, split_items

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$")
LIMITS = {
    "name": 100, "headline": 150, "email": 120, "phone": 40, "location": 100, "links": 1200,
    "summary": 1500, "skills": 4000, "projects": 9000, "experience": 9000, "education": 4000,
    "certifications": 2500, "additional": 4000,
}
MAX_ENTRIES, MAX_BULLETS, MAX_LINKS = 12, 12, 6
FIELDS = list(LIMITS)


def _clean(text: str) -> str:
    return _CONTROL.sub("", text or "").replace("\r\n", "\n").replace("\r", "\n")


# --- resume -> form ---------------------------------------------------------------------------

def _entries_to_text(entries: list[dict[str, Any]]) -> str:
    blocks = []
    for e in entries:
        lines = [e["heading"], *e["details"], *[f"- {b}" for b in e["bullets"]]]
        blocks.append("\n".join(line for line in lines if line))
    return "\n\n".join(blocks)


def resume_to_form(resume: Resume) -> dict[str, str]:
    skills = []
    for g in resume["skills"]:
        joined = ", ".join(g["items"])
        skills.append(f"{g['category']}: {joined}" if g["category"] else joined)
    extras = "\n\n".join("\n".join([f"## {x['title']}", *x["lines"]]) for x in resume["extras"])
    return {
        "name": resume["name"], "headline": resume["headline"], "email": resume["email"],
        "phone": resume["phone"], "location": resume["location"], "links": "\n".join(resume["links"]),
        "summary": resume["summary"], "skills": "\n".join(skills),
        "projects": _entries_to_text(resume["projects"]),
        "experience": _entries_to_text(resume["experience"]),
        "education": _entries_to_text(resume["education"]),
        "certifications": "\n".join(resume["certifications"]), "additional": extras,
    }


# --- form -> resume ----------------------------------------------------------------------------

def _text_to_entries(text: str) -> list[dict[str, Any]]:
    entries = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        entry: dict[str, Any] = {"heading": lines[0], "details": [], "bullets": []}
        for line in lines[1:]:
            if re.match(r"^[-*•]\s*", line):
                entry["bullets"].append(re.sub(r"^[-*•]\s*", "", line))
            elif entry["bullets"]:
                entry["bullets"].append(line)
            else:
                entry["details"].append(line)
        entries.append(entry)
    return entries


def _text_to_skills(text: str) -> list[dict[str, Any]]:
    groups = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^([^:,]{1,40}):\s*(.*)$", line)
        category, rest = (match.group(1).strip(), match.group(2)) if match else ("", line)
        items = split_items(rest)
        if items:
            groups.append({"category": category, "items": items})
    return groups


def _text_to_extras(text: str) -> list[dict[str, Any]]:
    extras: list[dict[str, Any]] = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("##"):
            extras.append({"title": line.lstrip("#").strip(), "lines": []})
        elif line and extras:
            extras[-1]["lines"].append(re.sub(r"^[-*•]\s*", "", line))
    return [x for x in extras if x["title"] and x["lines"]]


def form_to_resume(form: Mapping[str, str]) -> tuple[Resume, dict[str, str]]:
    """Validate and convert the editor form. Returns (resume, errors-by-field)."""
    values = {f: _clean(form.get(f, "")) for f in FIELDS}
    errors: dict[str, str] = {}
    for field, limit in LIMITS.items():
        if len(values[field]) > limit:
            errors[field] = f"Too long (maximum {limit:,} characters)."
    for field in ("name", "headline", "email", "phone", "location"):
        values[field] = " ".join(values[field].split())

    if not values["name"]:
        errors.setdefault("name", "Please enter your name.")
    if values["email"] and not _EMAIL.match(values["email"]):
        errors.setdefault("email", "Enter a valid email address.")
    links = [ln.strip() for ln in values["links"].split("\n") if ln.strip()]
    if len(links) > MAX_LINKS:
        errors.setdefault("links", f"At most {MAX_LINKS} links.")
    elif any(re.search(r"\s", ln) or "." not in ln for ln in links):
        errors.setdefault("links", "Each link must be on its own line, without spaces (e.g. github.com/you).")

    resume = empty_resume()
    resume.update(
        name=values["name"], headline=values["headline"], email=values["email"], phone=values["phone"],
        location=values["location"], links=links, summary=" ".join(values["summary"].split()),
        skills=_text_to_skills(values["skills"]),
        certifications=[ln.strip() for ln in values["certifications"].split("\n") if ln.strip()],
        extras=_text_to_extras(values["additional"]),
    )
    for key in ("projects", "experience", "education"):
        entries = _text_to_entries(values[key])
        if len(entries) > MAX_ENTRIES:
            errors.setdefault(key, f"At most {MAX_ENTRIES} entries.")
        elif any(len(e["bullets"]) > MAX_BULLETS for e in entries):
            errors.setdefault(key, f"At most {MAX_BULLETS} bullet points per entry.")
        elif any(len(t) > 400 for e in entries for t in (e["heading"], *e["details"], *e["bullets"])):
            errors.setdefault(key, "A line is too long (maximum 400 characters).")
        resume[key] = entries
    return resume, errors
