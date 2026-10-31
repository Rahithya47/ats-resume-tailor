"""Turn extracted resume text into a structured, editable resume dictionary.

The parser is heuristic: resumes have no standard layout. It aims to keep every
line of the original, never invent content, and leave the rest to the preview
editor, where the candidate can correct anything.

Resume shape
------------
{
  "name", "headline", "email", "phone", "location": str,
  "links": [str],
  "summary": str,
  "skills": [{"category": str, "items": [str]}],
  "projects" / "experience" / "education": [{"heading": str, "details": [str], "bullets": [str]}],
  "certifications": [str],
  "extras": [{"title": str, "lines": [str]}],
}
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

Resume = dict[str, Any]

SECTION_ALIASES: dict[str, set[str]] = {
    "summary": {"summary", "professional summary", "profile", "professional profile", "objective",
                "career objective", "about me", "about", "personal statement"},
    "skills": {"skills", "technical skills", "key skills", "core skills", "core competencies",
               "technologies", "tech stack", "technical proficiency", "skills and tools"},
    "projects": {"projects", "academic projects", "personal projects", "key projects",
                 "technical projects", "project work", "selected projects"},
    "experience": {"experience", "work experience", "professional experience", "internships",
                   "internship", "internship experience", "employment", "employment history",
                   "work history", "relevant experience"},
    "education": {"education", "academic background", "academics", "education and qualifications",
                  "educational qualifications", "qualifications", "academic qualifications"},
    "certifications": {"certifications", "certification", "certificates", "licenses and certifications",
                       "courses", "training", "certifications and courses", "courses and certifications"},
}
EXTRA_HEADINGS = {
    "achievements", "awards", "honors", "honours", "accomplishments", "activities",
    "extracurricular activities", "extracurriculars", "leadership", "publications", "languages",
    "interests", "hobbies", "volunteer", "volunteering", "volunteer experience",
    "positions of responsibility", "references", "awards and achievements",
    "achievements and awards", "key achievements",
}

_BULLET_RE = re.compile(
    r"^\s*(?:[•‣▪▫●◦⁃∙·■✓➢►]\s*|[-*–—]\s+)"
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_RE = re.compile(
    r"(?:https?://[^\s|,;]+|www\.[^\s|,;]+|(?:[A-Za-z0-9-]+\.)+(?:com|in|io|dev|me|net|org|ai|co)(?:/[^\s|,;]*)?)",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(r"(?<![\w/])\+?\d[\d\s().-]{8,}\d(?!\w)")
_LABEL_WORDS = re.compile(
    r"\b(?:e-?mail|phone|mobile|mob|tel|contact|linkedin|github|portfolio|website|web|location|address)\b\s*[:\-]?",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{4}\b|\b(?:19|20)\d{2}\b|\bpresent\b|\bcurrent\b",
    re.IGNORECASE,
)
_LABEL_RE = re.compile(
    r"^(?:tech(?:nologies)?(?: used)?|tools?|stack|link|links|github|demo|url|coursework|"
    r"relevant coursework|cgpa|gpa|grade|percentage|score|location|duration|role|company)\s*[:\-]",
    re.IGNORECASE,
)
_EDU_RE = re.compile(
    r"\b(?:b\.?\s?tech|m\.?\s?tech|b\.?e|m\.?e|b\.?sc|m\.?sc|bachelor|master|diploma|ph\.?d|mba|bca|mca|"
    r"intermediate|higher secondary|secondary|class\s?(?:x|xii|10|12)|ssc|hsc|cbse|icse|university|college|institute|school)\b",
    re.IGNORECASE,
)

_MONTHS = {"jan": "Jan", "feb": "Feb", "mar": "Mar", "apr": "Apr", "may": "May", "jun": "Jun",
           "jul": "Jul", "aug": "Aug", "sep": "Sep", "oct": "Oct", "nov": "Nov", "dec": "Dec"}
_MONTH_YEAR = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(?=(?:19|20)\d{2}\b)",
    re.IGNORECASE,
)
_RANGE_DASH = re.compile(
    r"(?<=\d{4})\s*[–—−-]\s*(?=(?:19|20)\d{2}\b|[A-Za-z]{3,9}\.? (?:19|20)\d{2}|present|current|ongoing)",
    re.IGNORECASE,
)
_RANGE_TO = re.compile(
    r"(?<=\d{4})\s+to\s+(?=(?:19|20)\d{2}\b|[A-Za-z]{3,9}\.? (?:19|20)\d{2}|present|current|ongoing)",
    re.IGNORECASE,
)
_PRESENT = re.compile(r"(?<= - )(?:present|current|till date|to date|ongoing)\b", re.IGNORECASE)


def empty_resume() -> Resume:
    return {
        "name": "", "headline": "", "email": "", "phone": "", "location": "", "links": [],
        "summary": "", "skills": [], "projects": [], "experience": [], "education": [],
        "certifications": [], "extras": [],
    }


def has_content(resume: Resume) -> bool:
    return bool(
        resume["summary"] or resume["skills"] or resume["projects"] or resume["experience"]
        or resume["education"] or resume["certifications"] or resume["extras"]
    )


def normalize_dates(text: str) -> str:
    """Make date ranges consistent: 'June 2024 – August 2024' -> 'Jun 2024 - Aug 2024'.

    Only touches month names directly before a year and ranges that follow a year.
    """
    if not text or not _DATE_RE.search(text):
        return text
    out = _MONTH_YEAR.sub(lambda m: _MONTHS[m.group(1)[:3].lower()] + " ", text)
    out = _RANGE_DASH.sub(" - ", out)
    out = _RANGE_TO.sub(" - ", out)
    return _PRESENT.sub("Present", out)


# --- Sections ---------------------------------------------------------------------

def _normalize_heading(line: str) -> str:
    cleaned = re.sub(r"[^a-z& ]", "", line.lower()).replace("&", "and")
    return " ".join(cleaned.split())


def _heading_key(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or len(stripped) > 45 or _BULLET_RE.match(stripped):
        return None
    norm = _normalize_heading(stripped)
    for key, aliases in SECTION_ALIASES.items():
        if norm in aliases:
            return key, stripped
    if norm in EXTRA_HEADINGS:
        title = stripped.strip(" :")
        return "extra", title.title() if title.isupper() else title
    return None


def _split_sections(lines: list[str]) -> tuple[list[str], list[tuple[str, str, list[str]]]]:
    header: list[str] = []
    sections: list[tuple[str, str, list[str]]] = []
    for line in lines:
        found = _heading_key(line)
        if found:
            sections.append((found[0], found[1], []))
        elif sections:
            sections[-1][2].append(line)
        else:
            header.append(line)
    return header, sections


# --- Header -------------------------------------------------------------------------

def _looks_like_name(line: str) -> bool:
    if re.search(r"[@\d]|https?://|www\.|[|,]", line) or _heading_key(line):
        return False
    tokens = line.split()
    if not 1 <= len(tokens) <= 6:
        return False
    return all(t[0].isalpha() and all(c.isalpha() or c in ".'’-" for c in t) for t in tokens)


def _parse_header(lines: list[str], resume: Resume) -> None:
    rows = [line.strip() for line in lines if line.strip()]
    name_idx = None
    for i, line in enumerate(rows[:4]):
        if _looks_like_name(line):
            resume["name"], name_idx = line, i
            break
    leftovers: list[str] = []
    for i, line in enumerate(rows):
        if i == name_idx:
            continue
        work = line
        emails = _EMAIL_RE.findall(work)
        work = _EMAIL_RE.sub(" ", work)
        urls = [u.rstrip(".,;)") for u in _URL_RE.findall(work)]
        work = _URL_RE.sub(" ", work)
        phones = [p.strip() for p in _PHONE_RE.findall(work)]
        work = _PHONE_RE.sub(" ", work)
        work = _LABEL_WORDS.sub(" ", work)
        if emails and not resume["email"]:
            resume["email"] = emails[0]
        if phones and not resume["phone"]:
            resume["phone"] = phones[0]
        for url in urls:
            if url not in resume["links"]:
                resume["links"].append(url)
        for token in re.split(r"\s*[|•·●▪]\s*|\s{3,}", work):
            token = token.strip(" ,;:-–—|")
            if len(token) >= 2:
                leftovers.append(token)
    for token in leftovers:
        if "," in token and not resume["location"] and len(token) <= 60:
            resume["location"] = token
        elif not resume["headline"]:
            resume["headline"] = token
        elif not resume["location"]:
            resume["location"] = token


# --- Skills ---------------------------------------------------------------------------

def split_items(text: str) -> list[str]:
    items: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if depth == 0 and ch in ",;|•·●":
            items.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    items.append("".join(buf))
    return _dedupe([i.strip().strip("-–—").strip().rstrip(".").strip() for i in items])


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for item in items:
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out


_SKILL_LABEL_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 &/+#.\-]{1,40}?)\s*:\s*(.*)$")


def _parse_skills(lines: list[str]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    prev = ""
    for raw in lines:
        line = _BULLET_RE.sub("", raw.strip(), count=1).strip()
        if not line:
            continue
        match = _SKILL_LABEL_RE.match(line)
        if match and "http" not in match.group(1).lower():
            groups.append({"category": match.group(1).strip(), "items": split_items(match.group(2))})
        elif groups and (line[0].islower() or prev.rstrip().endswith(",")):
            groups[-1]["items"] = _dedupe(groups[-1]["items"] + split_items(line))
        elif groups and groups[-1]["category"] == "":
            groups[-1]["items"] = _dedupe(groups[-1]["items"] + split_items(line))
        else:
            groups.append({"category": "", "items": split_items(line)})
        prev = line
    return [g for g in groups if g["items"]]


# --- Entries (projects / experience / education) -------------------------------------------

def _new_entry(heading: str) -> dict[str, Any]:
    return {"heading": heading, "details": [], "bullets": []}


def _entry_has_date(entry: dict[str, Any]) -> bool:
    return any(_DATE_RE.search(t) for t in [entry["heading"], *entry["details"]])


def _looks_like_heading(text: str) -> bool:
    if " | " in text or _DATE_RE.search(text):
        return True
    words = text.split()
    if not words or len(text) > 60 or text.endswith("."):
        return False
    return sum(1 for w in words if w[:1].isupper()) >= max(1, round(len(words) * 0.6))


def _is_continuation(prev: str, text: str) -> bool:
    if prev.endswith((".", "!", "?", ";", ":")):
        return text[:1].islower()
    if text[:1].islower():
        return True
    return len(prev) >= 70 and not _looks_like_heading(text)


def _classify(cur: dict[str, Any] | None, text: str, section: str, prev_blank: bool) -> str:
    if cur is None:
        return "new"
    if cur["bullets"]:
        if not prev_blank and _is_continuation(cur["bullets"][-1], text):
            return "continue"
        return "new"
    if prev_blank:
        return "new"
    if len(text) > 90 or text.endswith((".", "!")):
        return "bullet"
    if _LABEL_RE.match(text):
        return "detail"
    has_date = bool(_DATE_RE.search(text))
    if section in ("experience", "education"):
        if has_date and _entry_has_date(cur):
            return "new"
        if section == "education" and _EDU_RE.search(text) and _EDU_RE.search(cur["heading"]) and _entry_has_date(cur):
            return "new"
        return "detail" if len(cur["details"]) < 3 else "new"
    if has_date and not _entry_has_date(cur):
        return "detail"
    return "new" if _looks_like_heading(text) else "bullet"


def _parse_entries(lines: list[str], section: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    prev_blank = False
    for raw in lines:
        line = raw.strip()
        if not line:
            prev_blank = True
            continue
        is_bullet = bool(_BULLET_RE.match(line))
        text = _BULLET_RE.sub("", line, count=1).strip() if is_bullet else line
        if not text:
            continue
        if is_bullet:
            if cur is None:
                cur = _new_entry("")
                entries.append(cur)
            cur["bullets"].append(text)
        else:
            action = _classify(cur, text, section, prev_blank)
            if action == "new":
                cur = _new_entry(text)
                entries.append(cur)
            elif action == "detail":
                cur["details"].append(text)
            elif action == "bullet":
                cur["bullets"].append(text)
            else:
                cur["bullets"][-1] = f"{cur['bullets'][-1]} {text}".strip()
        prev_blank = False
    return [e for e in entries if e["heading"] or e["details"] or e["bullets"]]


def _parse_lines(lines: list[str]) -> list[str]:
    out = []
    for raw in lines:
        text = _BULLET_RE.sub("", raw.strip(), count=1).strip()
        if text:
            out.append(text)
    return out


# --- Public API --------------------------------------------------------------------------------

def parse_resume(raw_text: str) -> Resume:
    text = unicodedata.normalize("NFKC", raw_text or "").replace(" ", " ")
    lines = [line.rstrip() for line in text.replace("\r", "\n").split("\n")]
    header, sections = _split_sections(lines)
    resume = empty_resume()
    _parse_header(header, resume)
    for key, title, body in sections:
        if key == "summary":
            joined = " ".join(_parse_lines(body))
            resume["summary"] = f"{resume['summary']} {joined}".strip()
        elif key == "skills":
            resume["skills"].extend(_parse_skills(body))
        elif key in ("projects", "experience", "education"):
            resume[key].extend(_parse_entries(body, key))
        elif key == "certifications":
            resume["certifications"].extend(_parse_lines(body))
        else:
            lines_ = _parse_lines(body)
            if lines_:
                resume["extras"].append({"title": title, "lines": lines_})
    return resume
