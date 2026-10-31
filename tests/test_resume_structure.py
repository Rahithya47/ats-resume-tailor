import pytest

from app.services.keyword_extractor import extract_job_terms
from app.services.resume_structure import normalize_dates, parse_resume
from app.services.tailoring import GenerationError, generate_tailored_resume, tailor_resume
from tests.conftest import SAMPLE_JD, SAMPLE_RESUME


def _tailor(resume_text=SAMPLE_RESUME, jd=SAMPLE_JD, confirmed=None, title=""):
    terms = extract_job_terms(jd)
    return tailor_resume(parse_resume(resume_text), terms["required"], terms["preferred"], title, confirmed)


# --- parsing ----------------------------------------------------------------------------------

def test_header_fields():
    r = parse_resume(SAMPLE_RESUME)
    assert r["name"] == "Rahithya K"
    assert r["email"] == "rahithya@example.com"
    assert r["phone"] == "+91 98765 43210"
    assert r["location"] == "Hyderabad, India"
    assert r["links"] == ["linkedin.com/in/rahithya", "github.com/rahithya"]


def test_sections_parsed():
    r = parse_resume(SAMPLE_RESUME)
    assert r["summary"].startswith("Computer science student")
    assert [g["category"] for g in r["skills"]] == ["Languages", "Frameworks", "Tools"]
    assert r["skills"][0]["items"] == ["JS", "Python", "SQL"]
    assert [e["heading"] for e in r["projects"]] == ["Expense Tracker | Flask, SQLite", "Portfolio Website | HTML, CSS, JS"]
    assert len(r["projects"][0]["bullets"]) == 2
    assert r["experience"][0]["heading"].startswith("Software Intern")
    assert r["experience"][0]["bullets"] == ["Fixed bugs in a Python service", "Wrote SQL queries for reporting"]
    assert r["education"][0]["details"] == ["CGPA: 8.5"]
    assert r["certifications"] == ["Python for Everybody (Coursera)"]


@pytest.mark.parametrize("heading", ["PROFESSIONAL EXPERIENCE", "Work Experience", "Internships"])
def test_heading_variants(heading):
    r = parse_resume(f"Jane Doe\njane@example.com\n{heading}\nDev | Co | 2023 - 2024\n- Did work")
    assert len(r["experience"]) == 1


def test_skills_and_tools_heading_and_unlabelled_skills():
    r = parse_resume("Jane Doe\n\nSkills & Tools\nPython, SQL (PostgreSQL, MySQL), Git\n")
    assert r["skills"] == [{"category": "", "items": ["Python", "SQL (PostgreSQL, MySQL)", "Git"]}]


def test_wrapped_bullets_are_joined_and_markers_normalized():
    text = (
        "Jane Doe\n\nProjects\nApp | Python\n"
        "• Built a service that processes uploaded files and\nstores the results in a database\n"
        "• Added tests\n"
    )
    bullets = parse_resume(text)["projects"][0]["bullets"]
    assert bullets == ["Built a service that processes uploaded files and stores the results in a database", "Added tests"]


def test_unknown_sections_are_preserved_as_extras():
    r = parse_resume("Jane Doe\n\nSkills\nPython\n\nACHIEVEMENTS\n- Won a hackathon\n")
    assert r["extras"] == [{"title": "Achievements", "lines": ["Won a hackathon"]}]


def test_no_sections_gives_generation_error():
    with pytest.raises(GenerationError):
        generate_tailored_resume("Just a paragraph of text without any headings.", SAMPLE_JD)


@pytest.mark.parametrize("raw,expected", [
    ("June 2024 – August 2024", "Jun 2024 - Aug 2024"),
    ("Jan 2023-Mar 2024", "Jan 2023 - Mar 2024"),
    ("2021 to 2025", "2021 - 2025"),
    ("Sept 2022 — present", "Sep 2022 - Present"),
    ("5-day workshop", "5-day workshop"),          # not a date range: untouched
    ("Built Covid-19 tracker", "Built Covid-19 tracker"),
])
def test_normalize_dates(raw, expected):
    assert normalize_dates(raw) == expected


# --- tailoring ---------------------------------------------------------------------------------

def _text(resume):
    from app.services.tailoring import resume_text
    return resume_text(resume).casefold()


def test_never_adds_missing_skills():
    tailored, notes = _tailor()
    assert "docker" not in _text(tailored)
    assert "kubernetes" not in _text(tailored)
    assert any("Not added" in n and "Docker" in n for n in notes)


def test_skills_reordered_required_first_and_synonyms_reworded():
    tailored, _ = _tailor()
    langs = tailored["skills"][0]["items"]
    assert langs == ["Python", "SQL", "JavaScript"]          # JS -> JavaScript, required first
    assert tailored["skills"][2]["items"] == ["Git", "PostgreSQL"]


def test_synonyms_not_rewritten_unless_job_uses_the_term():
    tailored, _ = _tailor(jd="Requirements:\nPython, Flask")
    assert "JS" in tailored["skills"][0]["items"]
    assert "Postgres" in tailored["skills"][2]["items"]


def test_node_js_is_not_rewritten_as_javascript():
    resume = "Jane Doe\n\nProjects\nApp | Node JS\n- Built an API with Node JS and Flask\n"
    tailored, _ = _tailor(resume, jd="Requirements:\nJavaScript, Flask")
    assert "Node JS" in tailored["projects"][0]["bullets"][0]


def test_related_skills_are_not_treated_as_equivalent():
    resume = "Jane Doe\n\nSkills\nAngular, Azure\n"
    tailored, _ = _tailor(resume, jd="Requirements:\nReact, AWS")
    assert "react" not in _text(tailored) and "aws" not in _text(tailored)


def test_confirmed_skills_added_once_under_additional_skills():
    tailored, notes = _tailor(confirmed=["Docker", "Docker", "python"])
    last = tailored["skills"][-1]
    assert last == {"category": "Additional Skills", "items": ["Docker"]}
    assert "python" not in [i.casefold() for i in last["items"]]  # already in the resume
    assert any("confirmed" in n for n in notes)


def test_projects_reordered_by_relevance_and_experience_order_kept():
    resume = (
        "Jane Doe\n\nProjects\nBlog | HTML\n- Wrote static pages\n"
        "Shop | React, Flask\n- Built a React storefront with a Flask API\n\n"
        "Experience\nIntern | A Co | 2024 - 2025\n- Cleaned data\n- Built Flask endpoints\n"
        "Assistant | B Co | 2022 - 2023\n- Answered emails\n"
    )
    tailored, _ = _tailor(resume, jd="Requirements:\nReact, Flask")
    assert [p["heading"] for p in tailored["projects"]] == ["Shop | React, Flask", "Blog | HTML"]
    assert [e["heading"] for e in tailored["experience"]] == ["Intern | A Co | 2024 - 2025", "Assistant | B Co | 2022 - 2023"]
    assert tailored["experience"][0]["bullets"][0] == "Built Flask endpoints"  # most relevant bullet first


def test_summary_extended_not_invented():
    tailored, _ = _tailor()
    assert tailored["summary"].startswith("Computer science student who builds web applications.")
    assert "Key skills relevant to this role" in tailored["summary"]
    assert "Docker" not in tailored["summary"]


def test_generated_summary_when_missing_and_none_when_no_matches():
    resume = "Jane Doe\n\nSkills\nPython, Flask\n"
    tailored, _ = _tailor(resume, jd="Requirements:\nPython, Flask", title="Backend Developer")
    assert tailored["summary"] == "Backend Developer candidate with skills in Python and Flask."
    unrelated, _ = _tailor(resume, jd="Requirements:\nRust, Go")
    assert unrelated["summary"] == ""


def test_dates_normalized_in_tailored_output():
    tailored, _ = _tailor()
    assert tailored["experience"][0]["heading"].endswith("Jun 2024 - Aug 2024")
    assert tailored["education"][0]["heading"].endswith("2021 - 2025")


def test_original_resume_object_not_mutated():
    resume = parse_resume(SAMPLE_RESUME)
    snapshot = repr(resume)
    terms = extract_job_terms(SAMPLE_JD)
    tailor_resume(resume, terms["required"], terms["preferred"])
    assert repr(resume) == snapshot
