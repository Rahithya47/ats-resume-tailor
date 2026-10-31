"""Short-lived, in-memory store for the resume text and generated draft of one analysis.

Why it exists: generating and editing a tailored resume happens after the analysis request,
so the uploaded resume's text has to be kept somewhere. It is kept ONLY in this process's memory:
never written to disk, never put in the database/history, and discarded after a time limit
(CONTEXT_TTL_SECONDS, default 2 hours) or when the user presses "Discard my resume data".

Each entry is bound to the browser session that created it (signed cookie holds the tokens),
so another visitor cannot open or download someone else's draft by guessing a URL.
"""
from __future__ import annotations

import secrets
import threading
import time
from typing import Any, Callable

from flask import Flask, current_app, session

MAX_TOKENS_PER_SESSION = 20


class ContextStore:
    def __init__(self, ttl_seconds: float = 7200, max_items: int = 200, clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl_seconds
        self._max = max_items
        self._clock = clock
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def _purge(self) -> None:
        now = self._clock()
        for token in [t for t, (expires, _) in self._items.items() if expires <= now]:
            del self._items[token]

    def put(self, data: dict[str, Any]) -> str:
        with self._lock:
            self._purge()
            while len(self._items) >= self._max:
                del self._items[min(self._items, key=lambda k: self._items[k][0])]
            token = secrets.token_urlsafe(16)
            self._items[token] = (self._clock() + self._ttl, data)
            return token

    def get(self, token: str) -> dict[str, Any] | None:
        with self._lock:
            self._purge()
            item = self._items.get(token)
            if item is None:
                return None
            self._items[token] = (self._clock() + self._ttl, item[1])  # sliding expiry while in use
            return item[1]

    def delete(self, token: str) -> None:
        with self._lock:
            self._items.pop(token, None)

    def __len__(self) -> int:
        with self._lock:
            self._purge()
            return len(self._items)


def init_app(app: Flask) -> None:
    app.extensions["context_store"] = ContextStore(ttl_seconds=float(app.config["CONTEXT_TTL_SECONDS"]))


def _store() -> ContextStore:
    return current_app.extensions["context_store"]


def create_context(data: dict[str, Any]) -> str:
    token = _store().put(data)
    tokens = [t for t in session.get("ctx_tokens", []) if isinstance(t, str)] + [token]
    for dropped in tokens[:-MAX_TOKENS_PER_SESSION]:
        _store().delete(dropped)
    session["ctx_tokens"] = tokens[-MAX_TOKENS_PER_SESSION:]
    return token


def get_context(token: Any) -> dict[str, Any] | None:
    """Return the context only if it belongs to the current browser session and hasn't expired."""
    if not isinstance(token, str) or token not in session.get("ctx_tokens", []):
        return None
    return _store().get(token)


def discard_context(token: str) -> None:
    _store().delete(token)
    session["ctx_tokens"] = [t for t in session.get("ctx_tokens", []) if t != token]
