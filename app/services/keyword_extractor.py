"""Curated skills dictionary, job-requirement extraction and resume comparison."""
from __future__ import annotations

import re
from typing import Any

from app.services.text_cleaner import clean_text, redact_contact_details

# canonical name -> aliases that count as an *exact* match (synonyms/abbreviations only).
SKILLS: dict[str, list[str]] = {
    # Languages
    "python": ["python", "python3"],
    "java": ["java"],
    "javascript": ["javascript", "js", "ecmascript", "es6"],
    "typescript": ["typescript"],
    "c++": ["c++", "cpp"],
    "c#": ["c#", "csharp", "c sharp"],
    "go": ["golang"],
    "rust": ["rust"],
    "ruby": ["ruby"],
    "php": ["php"],
    "kotlin": ["kotlin"],
    "swift": ["swift"],
    "scala": ["scala"],
    "sql": ["sql"],
    "html": ["html", "html5"],
    "css": ["css", "css3"],
    "bash": ["bash", "shell scripting"],
    # Frameworks
    "react": ["react", "reactjs", "react.js"],
    "angular": ["angular", "angularjs"],
    "vue": ["vue", "vue.js", "vuejs"],
    "node.js": ["node.js", "nodejs"],
    "flask": ["flask"],
    "django": ["django"],
    "fastapi": ["fastapi"],
    "spring boot": ["spring boot", "springboot"],
    "spring": ["spring framework"],
    ".net": [".net", "dotnet", "asp.net"],
    # Tools / platforms
    "git": ["git"],
    "github": ["github"],
    "gitlab": ["gitlab"],
    "docker": ["docker"],
    "kubernetes": ["kubernetes", "k8s"],
    "aws": ["aws", "amazon web services"],
    "azure": ["azure", "microsoft azure"],
    "gcp": ["gcp", "google cloud", "google cloud platform"],
    "terraform": ["terraform"],
    "ansible": ["ansible"],
    "jenkins": ["jenkins"],
    "linux": ["linux"],
    "jira": ["jira"],
    "figma": ["figma"],
    # Data / databases
    "postgresql": ["postgresql", "postgres"],
    "mysql": ["mysql"],
    "sqlite": ["sqlite"],
    "mongodb": ["mongodb", "mongo db"],
    "redis": ["redis"],
    "elasticsearch": ["elasticsearch"],
    "kafka": ["kafka"],
    "rabbitmq": ["rabbitmq"],
    "pandas": ["pandas"],
    "numpy": ["numpy"],
    "tableau": ["tableau"],
    "power bi": ["power bi", "powerbi"],
    "excel": ["microsoft excel", "ms excel", "excel spreadsheets"],
    "data analysis": ["data analysis", "data analytics"],
    # ML
    "machine learning": ["machine learning", "ml"],
    "deep learning": ["deep learning"],
    "nlp": ["nlp", "natural language processing"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "tensorflow": ["tensorflow"],
    "pytorch": ["pytorch"],
    # Concepts / practices
    "rest apis": ["rest api", "rest apis", "restful", "restful api", "restful apis"],
    "graphql": ["graphql"],
    "microservices": ["microservices", "microservice"],
    "ci/cd": ["ci/cd", "ci cd", "continuous integration", "continuous delivery", "continuous deployment"],
    "testing": ["testing", "unit testing", "unit tests", "automated testing", "test automation", "tdd", "test-driven development"],
    "pytest": ["pytest"],
    "junit": ["junit"],
    "agile": ["agile", "scrum"],
    "oop": ["oop", "object-oriented", "object oriented"],
    "data structures": ["data structures"],
    "algorithms": ["algorithms"],
    "api design": ["api design"],
    # Soft skills
    "communication": ["communication", "communication skills"],
    "leadership": ["leadership"],
    "problem solving": ["problem solving", "problem-solving"],
    "project management": ["project management"],
}

DISPLAY_OVERRIDES = {
    "sql": "SQL", "aws": "AWS", "gcp": "GCP", "html": "HTML", "css": "CSS", "php": "PHP",
    "nlp": "NLP", "oop": "OOP", "ci/cd": "CI/CD", "rest apis": "REST APIs", "graphql": "GraphQL",
    "fastapi": "FastAPI", "postgresql": "PostgreSQL", "mysql": "MySQL", "sqlite": "SQLite",
    "mongodb": "MongoDB", "javascript": "JavaScript", "typescript": "TypeScript",
    "rabbitmq": "RabbitMQ", "pytorch": "PyTorch", "tensorflow": "TensorFlow",
    "github": "GitHub", "gitlab": "GitLab", "power bi": "Power BI", "scikit-learn": "scikit-learn",
    ".net": ".NET", "junit": "JUnit", "pytest": "pytest", "api design": "API design",
    "node.js": "Node.js", "kubernetes": "Kubernetes", "elasticsearch": "Elasticsearch",
}

# Groups of related-but-NOT-interchangeable skills. Being in one group never counts as a match.
RELATED_GROUPS: list[set[str]] = [
    {"react", "angular", "vue"},
    {"aws", "azure", "gcp"},
    {"django", "flask", "fastapi"},
    {"postgresql", "mysql", "sqlite", "sql"},
    {"docker", "kubernetes"},
    {"tensorflow", "pytorch", "scikit-learn", "machine learning", "deep learning"},
    {"git", "github", "gitlab"},
    {"testing", "pytest", "junit"},
    {"ci/cd", "jenkins"},
    {"javascript", "typescript", "node.js"},
    {"java", "kotlin", "scala", "spring boot", "spring"},
    {"kafka", "rabbitmq"},
    {"tableau", "power bi"},
]

RELATED: dict[str, set[str]] = {}
for _group in RELATED_GROUPS:
    for _term in _group:
        RELATED.setdefault(_term, set()).update(_group - {_term})


def display_name(canonical: str) -> str:
    if canonical in DISPLAY_OVERRIDES:
        return DISPLAY_OVERRIDES[canonical]
    return " ".join(word.capitalize() for word in canonical.split(" "))


def _compile(aliases: list[str]) -> re.Pattern[str]:
    ordered = sorted(set(aliases), key=len, reverse=True)
    body = "|".join(re.escape(a) for a in ordered)
    # Don't match inside longer tokens ("java" in "javascript", "js" in "node.js").
    return re.compile(rf"(?<![A-Za-z0-9+#.])(?:{body})(?![A-Za-z0-9+#])", re.IGNORECASE)


_PATTERNS = {canonical: _compile(aliases) for canonical, aliases in SKILLS.items()}


def find_skills(text: str) -> dict[str, tuple[int, int]]:
    """Return {canonical skill: (start, end)} of its first match, ordered by position."""
    hits: dict[str, tuple[int, int]] = {}
    for canonical, pattern in _PATTERNS.items():
        match = pattern.search(text)
        if match:
            hits[canonical] = (match.start(), match.end())
    return dict(sorted(hits.items(), key=lambda item: item[1][0]))


# --- Job description sections ------------------------------------------------

_PREFERRED_HEADING = re.compile(
    r"^\s*(?:preferred|nice[\s-]to[\s-]haves?|bonus|good[\s-]to[\s-]have|desirable|optional|pluses|plus)\b",
    re.IGNORECASE,
)
_REQUIRED_HEADING = re.compile(
    r"^\s*(?:requirements?|required|qualifications?|must[\s-]have|minimum|basic|responsibilities|"
    r"what you(?:'ll| will)? (?:need|bring)|you have)\b",
    re.IGNORECASE,
)
_PREFERRED_INLINE = re.compile(
    r"\b(?:nice[\s-]to[\s-]have|preferred|(?:is|are) a plus|a plus|bonus|good to have|desirable)\b",
    re.IGNORECASE,
)


def extract_job_terms(jd_text: str) -> dict[str, list[str]]:
    """Split skills in a job description into required and preferred lists.

    Skills default to *required*. They become *preferred* under a heading such as
    "Nice to have" or on a line containing phrases like "a plus". If a skill appears
    in both places, required wins.
    """
    required: dict[str, None] = {}
    preferred: dict[str, None] = {}
    mode = "required"
    for line in clean_text(jd_text, keep_lines=True).splitlines():
        short = len(line) <= 60
        if short and _PREFERRED_HEADING.match(line):
            mode = "preferred"
        elif short and _REQUIRED_HEADING.match(line):
            mode = "required"
        is_preferred = mode == "preferred" or bool(_PREFERRED_INLINE.search(line))
        target = preferred if is_preferred else required
        for skill in find_skills(line):
            target.setdefault(skill, None)
    return {
        "required": list(required),
        "preferred": [s for s in preferred if s not in required],
    }


# --- Comparison -----------------------------------------------------------------

def _snippet(text: str, start: int, end: int, width: int = 60) -> str:
    left, right = max(0, start - width), min(len(text), end + width)
    snippet = text[left:right].strip()
    snippet = ("…" if left > 0 else "") + snippet + ("…" if right < len(text) else "")
    return redact_contact_details(snippet)


def compare_terms(resume_text: str, required: list[str], preferred: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Classify each job skill as matched, missing, or (missing but) related.

    `related` is informational: it never counts as a match and is a subset of `missing`.
    """
    resume = clean_text(resume_text)
    resume_hits = find_skills(resume)
    matched: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    related: list[dict[str, Any]] = []
    for level, terms in (("required", required), ("preferred", preferred)):
        for term in terms:
            if term in resume_hits:
                start, end = resume_hits[term]
                matched.append(
                    {"term": display_name(term), "level": level, "evidence": _snippet(resume, start, end)}
                )
                continue
            missing.append({"term": display_name(term), "level": level})
            have = sorted(display_name(r) for r in RELATED.get(term, ()) if r in resume_hits)
            if have:
                related.append({"term": display_name(term), "level": level, "resume_has": have})
    return {"matched": matched, "missing": missing, "related": related}
