"""End-of-session retry round for vocab cards.

Cards rated `again` or `hard` during a vocab session are remembered here so
the learner can be asked them once more before the session ends. The retry is
only a short memory rewind: nothing in this module touches FSRS state, and a
retry result never changes a card's schedule.

State lives in `<lang_dir>/vocab-session.json` and is dropped when the vocab
session is logged (`session-log --type vocab`). A file left over from an
earlier day is treated as empty, so an abandoned session can't leak into a
later one.
"""
from __future__ import annotations

from datetime import date

STATE_NAME = "vocab-session"
RETRY_RATINGS = ("again", "hard")
DEFAULT_MAX_ATTEMPTS = 2

_SEVERITY = {"hard": 1, "again": 2}


def empty_state(today: date) -> dict:
    return {"schema_version": 1, "date": today.isoformat(), "failed": {}}


def _fresh(state: dict, today: date) -> dict:
    """The state for `today`: a stale or empty file becomes a clean state."""
    if state.get("date") != today.isoformat() or "failed" not in state:
        return empty_state(today)
    return state


def record_failure(state: dict, card_id: str, rating: str, today: date) -> dict:
    """Remember a card rated again/hard. A repeat keeps the worse rating."""
    state = _fresh(state, today)
    entry = state["failed"].get(card_id)
    if entry is None:
        state["failed"][card_id] = {"rating": rating, "attempts": 0, "fixed": False}
    elif _SEVERITY[rating] > _SEVERITY[entry["rating"]]:
        entry["rating"] = rating
    return state


def pending(state: dict, today: date, max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> list[dict]:
    """Cards still to be asked: not yet answered correctly, attempts left.

    `again` cards come first, then `hard`; failure order is kept within each.
    """
    state = _fresh(state, today)
    rows = [
        {"id": cid, **entry}
        for cid, entry in state["failed"].items()
        if not entry["fixed"] and entry["attempts"] < max_attempts
    ]
    rows.sort(key=lambda r: -_SEVERITY[r["rating"]])  # stable: keeps failure order
    return rows


def record_attempt(state: dict, card_id: str, correct: bool, today: date) -> dict:
    state = _fresh(state, today)
    entry = state["failed"].get(card_id)
    if entry is None:
        raise KeyError(card_id)
    entry["attempts"] += 1
    if correct:
        entry["fixed"] = True
    return state


def counts(state: dict, today: date) -> dict:
    state = _fresh(state, today)
    failed = state["failed"]
    return {
        "failed": len(failed),
        "fixed": sum(1 for e in failed.values() if e["fixed"]),
    }
