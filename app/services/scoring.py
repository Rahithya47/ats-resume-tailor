"""Explainable keyword-coverage score.

Formula
-------
coverage(group) = matched_in_group / total_in_group * 100

overall = 0.8 * required_coverage + 0.2 * preferred_coverage
          (if only one group exists in the posting, overall = that group's coverage;
           if neither exists, there is no score)

Only exact matches (including listed aliases such as JS = JavaScript) count.
Related terms never add to the score.

Limitations: this measures overlap with a curated skills dictionary. It does not
read context, seniority, years of experience, or formatting, and it is NOT an
official ATS score or a prediction of hiring outcomes.
"""
from __future__ import annotations

from typing import Any

REQUIRED_WEIGHT = 0.8
PREFERRED_WEIGHT = 0.2


def coverage(matched: int, total: int) -> float | None:
    """Percentage of matched terms, or None when the group is empty."""
    if matched < 0 or total < 0 or matched > total:
        raise ValueError("matched must be between 0 and total")
    if total == 0:
        return None
    return round(matched / total * 100, 1)


def calculate_score(
    required_total: int, required_matched: int, preferred_total: int, preferred_matched: int
) -> dict[str, Any]:
    required_cov = coverage(required_matched, required_total)
    preferred_cov = coverage(preferred_matched, preferred_total)

    if required_cov is not None and preferred_cov is not None:
        overall: float | None = round(REQUIRED_WEIGHT * required_cov + PREFERRED_WEIGHT * preferred_cov, 1)
    elif required_cov is not None:
        overall = required_cov
    else:
        overall = preferred_cov  # may be None if the posting had no recognized skills

    return {
        "overall": overall,
        "required_total": required_total,
        "required_matched": required_matched,
        "required_coverage": required_cov,
        "preferred_total": preferred_total,
        "preferred_matched": preferred_matched,
        "preferred_coverage": preferred_cov,
        "weights": {"required": REQUIRED_WEIGHT, "preferred": PREFERRED_WEIGHT},
    }
