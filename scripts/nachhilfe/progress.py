"""Deterministic aggregation: streaks, hour totals, progress %, mastery
buckets, rolling averages. Every number shown to the learner comes from
here — never estimated or recomputed by the model.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

LEVELS = ["0", "A1", "A2", "B1", "B2", "C1", "C2"]


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def hours_between(current_level: str, aim_level: str, transitions: dict) -> float:
    start = LEVELS.index(current_level)
    end = LEVELS.index(aim_level)
    if end <= start:
        return 0.0
    total = 0.0
    for i in range(start, end):
        key = f"{LEVELS[i]}->{LEVELS[i + 1]}"
        total += transitions.get(key, 0)
    return total


def daily_minutes_target(hours_needed: float, days_available: int, rest_days_per_week: int = 1) -> float:
    if days_available <= 0:
        return 0.0
    practice_days = days_available * (7 - rest_days_per_week) / 7
    if practice_days <= 0:
        return 0.0
    return (hours_needed * 60) / practice_days


def hours_done(sessions: list[dict]) -> float:
    return sum(s.get("minutes", 0) for s in sessions) / 60


def progress_bar(done: float, total: float, width: int = 20) -> str:
    if total <= 0:
        filled = width
    else:
        filled = round(width * min(done / total, 1.0))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def compute_streak(sessions: list[dict], today: date) -> dict:
    day_set = {_parse_date(s["date"]) for s in sessions}
    if not day_set:
        return {"current": 0, "longest": 0, "last_active_date": None}

    current = 0
    cursor = today if today in day_set else today - timedelta(days=1)
    while cursor in day_set:
        current += 1
        cursor -= timedelta(days=1)

    longest = 0
    run = 0
    prev = None
    for d in sorted(day_set):
        run = run + 1 if prev is not None and (d - prev).days == 1 else 1
        longest = max(longest, run)
        prev = d

    return {
        "current": current,
        "longest": longest,
        "last_active_date": max(day_set).isoformat(),
    }


def active_days_table(sessions: list[dict], n: int = 10) -> list[dict]:
    by_day: dict[str, dict] = defaultdict(lambda: {"count": 0, "minutes": 0})
    for s in sessions:
        entry = by_day[s["date"]]
        entry["count"] += 1
        entry["minutes"] += s.get("minutes", 0)
    days = sorted(by_day.keys(), reverse=True)[:n]
    return [{"date": d, **by_day[d]} for d in days]


def last_n_sessions(sessions: list[dict], n: int = 10) -> list[dict]:
    """Most recent first. Within a day, order by `logged_at` when present;
    sessions logged before that field existed fall back to file order (the
    list is append-only, so a later index is a later session)."""
    indexed = list(enumerate(sessions))
    indexed.sort(key=lambda p: (p[1]["date"], p[1].get("logged_at", ""), p[0]), reverse=True)
    return [s for _, s in indexed[:n]]


def mastery_breakdown(cards: list[dict], very_good_days: float, good_days: float) -> dict:
    counts = {"very_good": 0, "good": 0, "in_learning": 0}
    for c in cards:
        stability = c.get("stability")
        if c.get("state") != "review" or stability is None:
            counts["in_learning"] += 1
        elif stability >= very_good_days:
            counts["very_good"] += 1
        elif stability >= good_days:
            counts["good"] += 1
        else:
            counts["in_learning"] += 1
    return counts


def discipline_scores(sessions: list[dict], session_type: str) -> list[dict]:
    filtered = [s for s in sessions if s.get("type") == session_type and s.get("score") is not None]
    return sorted(filtered, key=lambda s: s["date"])


def rolling_average(sessions: list[dict], session_type: str, n: int = 5) -> float | None:
    scored = discipline_scores(sessions, session_type)
    if not scored:
        return None
    recent = scored[-n:]
    return sum(s["score"] for s in recent) / len(recent)


def score_history_table(sessions: list[dict], session_type: str) -> list[dict]:
    """Per-session scores if <=10 sessions logged; weekly once past that;
    monthly once the weekly table itself would grow past ~40 points."""
    scored = discipline_scores(sessions, session_type)
    if len(scored) <= 10:
        return [{"period": s["date"], "score": s["score"]} for s in scored]

    monthly = len(scored) > 40

    def bucket_key(d: date) -> str:
        if monthly:
            return d.strftime("%Y-%m")
        iso = d.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    buckets: dict[str, list[float]] = defaultdict(list)
    for s in scored:
        buckets[bucket_key(_parse_date(s["date"]))].append(s["score"])

    return [{"period": k, "score": sum(v) / len(v)} for k, v in sorted(buckets.items())]


def weak_grammar_topics(mistake_counts: dict, limit: int = 5) -> list[list]:
    ranked = sorted(mistake_counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [[topic, count] for topic, count in ranked]
