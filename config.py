"""Application configuration, driven by environment variables."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _database_path() -> str:
    configured = os.environ.get("DATABASE")
    if configured:
        path = Path(configured)
        return str(path if path.is_absolute() else BASE_DIR / path)
    if os.environ.get("VERCEL"):
        return "/tmp/ats_resume_tailor.db"  # only writable location on Vercel
    return str(BASE_DIR / "instance" / "ats_resume_tailor.db")


class Config:
    # If SECRET_KEY is not set, a random key is generated for this run only.
    # Sessions/CSRF tokens then reset on restart. Set it in .env for stability.
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    MAX_UPLOAD_MB = float(os.environ.get("MAX_UPLOAD_MB", "5"))
    DATABASE = _database_path()

    # Where temporary upload files are written (None = system temp dir).
    UPLOAD_TMP_DIR = os.environ.get("UPLOAD_TMP_DIR") or None

    # How long resume text/drafts stay in server memory (never on disk) for tailoring. Seconds.
    CONTEXT_TTL_SECONDS = float(os.environ.get("CONTEXT_TTL_SECONDS", "7200"))

    MAX_JOB_DESCRIPTION_CHARS = 20_000
    MIN_JOB_DESCRIPTION_CHARS = 20
    MAX_FIELD_CHARS = 120

    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
