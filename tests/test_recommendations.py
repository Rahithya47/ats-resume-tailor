from app.services.recommendations import generate_recommendations
from app.services.scoring import calculate_score


def _recs(matched=(), missing=(), related=(), totals=(0, 0, 0, 0)):
    return generate_recommendations(list(matched), list(missing), list(related), calculate_score(*totals))


def test_missing_required_is_high_priority_and_first():
    recs = _recs(missing=[{"term": "Docker", "level": "required"}], totals=(1, 0, 0, 0))
    assert recs[0]["priority"] == "high"
    assert "Docker" in recs[0]["detail"]


def test_top_five_only_then_remainder_note():
    missing = [{"term": f"Skill{i}", "level": "required"} for i in range(7)]
    recs = _recs(missing=missing, totals=(7, 0, 0, 0))
    assert "Skill4" in recs[0]["detail"] and "Skill5" not in recs[0]["detail"]
    assert any("Skill5" in r["detail"] for r in recs)


def test_related_recommendation_warns_not_interchangeable():
    related = [{"term": "AWS", "level": "required", "resume_has": ["Azure"]}]
    recs = _recs(missing=[{"term": "AWS", "level": "required"}], related=related, totals=(1, 0, 0, 0))
    assert any("not interchangeable" in r["detail"] for r in recs)


def test_always_includes_honesty_guidance():
    recs = _recs(totals=(1, 1, 0, 0))
    assert any(r["title"] == "Only add what is true" for r in recs)
    assert [r["priority"] for r in recs] == sorted([r["priority"] for r in recs], key=["high", "medium", "low"].index)


def test_empty_keyword_set_guidance():
    recs = _recs()
    assert recs[0]["priority"] == "high"
    assert "No recognizable skills" in recs[0]["title"]
