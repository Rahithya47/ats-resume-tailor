"""Orchestrates extraction, comparison, scoring and recommendations."""
from __future__ import annotations

from typing import Any

from app.services.keyword_extractor import compare_terms, extract_job_terms
from app.services.recommendations import generate_recommendations
from app.services.scoring import calculate_score


def run_analysis(resume_text: str, job_description: str) -> dict[str, Any]:
    terms = extract_job_terms(job_description)
    comparison = compare_terms(resume_text, terms["required"], terms["preferred"])

    def count(items: list[dict[str, Any]], level: str) -> int:
        return sum(1 for item in items if item["level"] == level)

    breakdown = calculate_score(
        required_total=len(terms["required"]),
        required_matched=count(comparison["matched"], "required"),
        preferred_total=len(terms["preferred"]),
        preferred_matched=count(comparison["matched"], "preferred"),
    )
    return {
        "match_score": breakdown["overall"],
        "breakdown": breakdown,
        "matched": comparison["matched"],
        "missing": comparison["missing"],
        "related": comparison["related"],
        "recommendations": generate_recommendations(
            comparison["matched"], comparison["missing"], comparison["related"], breakdown
        ),
    }
