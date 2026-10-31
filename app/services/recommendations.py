"""Evidence-based suggestions. Nothing here invents skills or achievements."""
from __future__ import annotations

from typing import Any

_ORDER = {"high": 0, "medium": 1, "low": 2}


def _join(terms: list[str]) -> str:
    return ", ".join(terms)


def generate_recommendations(
    matched: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    related: list[dict[str, Any]],
    breakdown: dict[str, Any],
) -> list[dict[str, str]]:
    recs: list[dict[str, str]] = []
    total_terms = breakdown["required_total"] + breakdown["preferred_total"]

    if total_terms == 0:
        recs.append(
            {
                "priority": "high",
                "title": "No recognizable skills found in the job description",
                "detail": "Paste the full posting, including the requirements section. The analyzer "
                "only recognizes skills in its built-in dictionary, so unusual or niche terms are not covered.",
            }
        )

    missing_required = [m["term"] for m in missing if m["level"] == "required"]
    missing_preferred = [m["term"] for m in missing if m["level"] == "preferred"]

    if missing_required:
        top = missing_required[:5]
        recs.append(
            {
                "priority": "high",
                "title": f"Review {len(top)} missing required skill{'s' if len(top) != 1 else ''}",
                "detail": f"The posting asks for {_join(top)}, which was not found in your resume. "
                "If you genuinely have this experience, add a concrete example (project, role, or result). "
                "If you don't, leave it out.",
            }
        )
        if len(missing_required) > 5:
            recs.append(
                {
                    "priority": "medium",
                    "title": "More required skills are missing",
                    "detail": f"Also not found: {_join(missing_required[5:])}.",
                }
            )

    for item in related[:3]:
        recs.append(
            {
                "priority": "medium",
                "title": f"Check how you describe {item['term']}",
                "detail": f"Your resume mentions {_join(item['resume_has'])}, which is related to {item['term']} "
                "but not interchangeable. If you have used "
                f"{item['term']} directly, say so explicitly; otherwise don't claim it.",
            }
        )

    if missing_preferred:
        recs.append(
            {
                "priority": "low",
                "title": "Optional: preferred skills not found",
                "detail": f"Nice-to-have skills not found: {_join(missing_preferred[:5])}. "
                "These matter less; mention them only if accurate.",
            }
        )

    if total_terms and not missing_required:
        recs.append(
            {
                "priority": "medium",
                "title": "All required skills were found",
                "detail": "Make sure each one is backed by specific evidence (what you built or achieved), "
                "not just listed in a skills section.",
            }
        )

    recs.append(
        {
            "priority": "low",
            "title": "Make relevant experience easy to find",
            "detail": "Place the most relevant projects and roles near the top and use the posting's "
            "terminology naturally and accurately.",
        }
    )
    recs.append(
        {
            "priority": "low",
            "title": "Only add what is true",
            "detail": "Include measurable outcomes only when you can verify them, and never add skills "
            "just to raise the score.",
        }
    )
    return sorted(recs, key=lambda r: _ORDER[r["priority"]])
