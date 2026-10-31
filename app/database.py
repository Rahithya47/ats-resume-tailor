"""SQLite access. All queries are parameterized. No resume text is ever stored."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from flask import Flask, current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_title TEXT NOT NULL DEFAULT '',
    company_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    match_score REAL,
    matched_keywords TEXT NOT NULL DEFAULT '[]',
    missing_keywords TEXT NOT NULL DEFAULT '[]',
    related_keywords TEXT NOT NULL DEFAULT '[]',
    score_breakdown TEXT NOT NULL DEFAULT '{}',
    recommendations TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses (created_at DESC);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_exc: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    get_db().executescript(SCHEMA)


def init_app(app: Flask) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(app.config["DATABASE"])), exist_ok=True)
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()


# --- JSON helpers -----------------------------------------------------------

def _load(raw: str, expected: type, default: Any) -> Any:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return default
    return value if isinstance(value, expected) else default


def _keyword_items(raw: str, extra: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    items = []
    for item in _load(raw, list, []):
        if not isinstance(item, dict):
            continue
        clean: dict[str, Any] = {
            "term": str(item.get("term", ""))[:80],
            "level": item.get("level") if item.get("level") in ("required", "preferred") else "required",
        }
        if "resume_has" in extra:
            clean["resume_has"] = [str(x)[:80] for x in item.get("resume_has", []) if isinstance(x, str)]
        items.append(clean)
    return items


def _row_to_analysis(row: sqlite3.Row) -> dict[str, Any]:
    recs = [
        {
            "priority": str(r.get("priority", "low")),
            "title": str(r.get("title", "")),
            "detail": str(r.get("detail", "")),
        }
        for r in _load(row["recommendations"], list, [])
        if isinstance(r, dict)
    ]
    return {
        "id": row["id"],
        "job_title": row["job_title"],
        "company_name": row["company_name"],
        "created_at": row["created_at"],
        "match_score": row["match_score"],
        "matched": _keyword_items(row["matched_keywords"]),
        "missing": _keyword_items(row["missing_keywords"]),
        "related": _keyword_items(row["related_keywords"], extra=("resume_has",)),
        "breakdown": _load(row["score_breakdown"], dict, {}),
        "recommendations": recs,
    }


# --- Queries ----------------------------------------------------------------

def insert_analysis(job_title: str, company_name: str, result: dict[str, Any]) -> int:
    """Store an analysis. Evidence snippets (resume text) are deliberately dropped."""
    matched = [{"term": m["term"], "level": m["level"]} for m in result["matched"]]
    db = get_db()
    cursor = db.execute(
        "INSERT INTO analyses (job_title, company_name, created_at, match_score, "
        "matched_keywords, missing_keywords, related_keywords, score_breakdown, recommendations) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            job_title,
            company_name,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            result["match_score"],
            json.dumps(matched),
            json.dumps(result["missing"]),
            json.dumps(result["related"]),
            json.dumps(result["breakdown"]),
            json.dumps(result["recommendations"]),
        ),
    )
    db.commit()
    return int(cursor.lastrowid)


def list_analyses(limit: int | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM analyses ORDER BY created_at DESC, id DESC"
    params: tuple = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (int(limit),)
    return [_row_to_analysis(r) for r in get_db().execute(sql, params).fetchall()]


def get_analysis(analysis_id: int) -> dict[str, Any] | None:
    row = get_db().execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
    return _row_to_analysis(row) if row else None


def delete_analysis(analysis_id: int) -> bool:
    db = get_db()
    cursor = db.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
    db.commit()
    return cursor.rowcount > 0


def delete_all_analyses() -> int:
    db = get_db()
    cursor = db.execute("DELETE FROM analyses")
    db.commit()
    return cursor.rowcount


def count_analyses() -> int:
    return int(get_db().execute("SELECT COUNT(*) FROM analyses").fetchone()[0])
