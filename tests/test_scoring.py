import pytest

from app.services.analysis import run_analysis
from app.services.keyword_extractor import compare_terms, extract_job_terms, find_skills
from app.services.scoring import calculate_score, coverage


def test_coverage_basic_and_empty():
    assert coverage(12, 20) == 60.0
    assert coverage(0, 0) is None


@pytest.mark.parametrize("matched,total", [(-1, 5), (6, 5), (1, -1)])
def test_coverage_invalid(matched, total):
    with pytest.raises(ValueError):
        coverage(matched, total)


def test_weighted_score():
    result = calculate_score(4, 3, 1, 0)
    assert result["required_coverage"] == 75.0
    assert result["preferred_coverage"] == 0.0
    assert result["overall"] == 60.0


def test_score_single_group_and_empty():
    assert calculate_score(4, 2, 0, 0)["overall"] == 50.0
    assert calculate_score(0, 0, 2, 1)["overall"] == 50.0
    assert calculate_score(0, 0, 0, 0)["overall"] is None  # no division by zero


def test_alias_mapping():
    assert "javascript" in find_skills("Experienced with JS and ES6")
    assert "kubernetes" in find_skills("k8s clusters")
    assert "postgresql" in find_skills("Postgres tuning")


def test_java_is_not_javascript():
    assert "java" not in find_skills("Expert in JavaScript")
    assert "javascript" not in find_skills("Expert in Java")


def test_special_character_skills():
    hits = find_skills("C++ and C# and Node.js and CI/CD")
    assert {"c++", "c#", "node.js", "ci/cd"} <= set(hits)
    assert "javascript" not in find_skills("Node.js services")  # "js" inside node.js


def test_required_vs_preferred_sections():
    terms = extract_job_terms("Requirements:\nPython, Docker\nNice to have:\nKubernetes\n")
    assert terms["required"] == ["python", "docker"]
    assert terms["preferred"] == ["kubernetes"]


def test_inline_preferred_and_required_wins():
    terms = extract_job_terms("Python required.\nDocker experience is a plus.\nPython is also nice to have.")
    assert "docker" in terms["preferred"]
    assert "python" in terms["required"] and "python" not in terms["preferred"]


def test_matched_missing_classification():
    result = compare_terms("I use Python and Flask.", ["python", "docker"], ["kubernetes"])
    assert [m["term"] for m in result["matched"]] == ["Python"]
    assert {m["term"] for m in result["missing"]} == {"Docker", "Kubernetes"}
    assert "Python" in result["matched"][0]["evidence"]


def test_related_is_not_a_match():
    result = compare_terms("Deployed services on Azure.", ["aws"], [])
    assert result["matched"] == []
    assert result["missing"] == [{"term": "AWS", "level": "required"}]
    assert result["related"] == [{"term": "AWS", "level": "required", "resume_has": ["Azure"]}]


def test_react_angular_not_interchangeable():
    result = compare_terms("Built apps in Angular.", ["react"], [])
    assert result["matched"] == []
    assert result["related"][0]["resume_has"] == ["Angular"]


def test_evidence_redacts_contact_details():
    result = compare_terms("Reach me: jane@example.com 555-123-4567 Python dev", ["python"], [])
    evidence = result["matched"][0]["evidence"]
    assert "jane@example.com" not in evidence
    assert "555-123-4567" not in evidence


def test_run_analysis_end_to_end():
    jd = "Requirements:\nPython, Flask, SQL, Docker\nNice to have:\nKubernetes"
    result = run_analysis("Python Flask SQL developer", jd)
    assert result["match_score"] == 60.0
    assert result["breakdown"]["required_matched"] == 3


def test_run_analysis_no_keywords():
    result = run_analysis("Python developer", "We are a friendly team looking for a great colleague.")
    assert result["match_score"] is None
    assert result["recommendations"][0]["priority"] == "high"
