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


CHART_WIDTH = 56
CHART_HEIGHT = 11  # odd, so the middle label is exactly half of the top one
AXIS_DATE_FORMAT = "%d.%m."  # day.month, as in the learner's region (de-DE)
CAPTION_DATE_FORMAT = "%d.%m.%Y"


def cumulative_hours(sessions: list[dict], start: date, end: date) -> list[float]:
    """Running total of hours studied: 0 at the start of `start`, then the total
    at the end of each day through `end` (so `days + 1` values)."""
    minutes_by_day: dict[date, int] = defaultdict(int)
    for s in sessions:
        minutes_by_day[_parse_date(s["date"])] += s.get("minutes", 0)
    series = [0.0]
    total = 0
    day = start
    while day <= end:
        total += minutes_by_day.get(day, 0)
        series.append(total / 60)
        day += timedelta(days=1)
    return series


def progress_chart(
    sessions: list[dict],
    first_day: str | None,
    today: date,
    width: int = CHART_WIDTH,
    height: int = CHART_HEIGHT,
) -> dict:
    """Line chart of cumulative study hours, ready to print in a code block.

    The line starts at 0 on the first day (the profile's creation date, or the
    first logged session if that is earlier) and ends at today's total. The
    vertical scale runs from 0 to that total, so the line always reaches the
    top row; the progress bar shows how far that is from the goal. When there
    are more days than columns the days are sampled evenly, first and last
    point included.
    """
    session_days = [_parse_date(s["date"]) for s in sessions]
    first_days = ([_parse_date(first_day)] if first_day else []) + session_days
    start = min(first_days) if first_days else today
    end = max([today] + session_days)
    series = cumulative_hours(sessions, start, end)
    total = series[-1]

    cols = min(len(series), width)  # at least 2: the zero point and one day
    picks = [round(i * (len(series) - 1) / (cols - 1)) for i in range(cols)]
    top = total if total > 0 else 1.0
    rows = [round(series[i] / top * (height - 1)) for i in picks]

    grid = [[" "] * cols for _ in range(height)]  # grid[0] is the top row
    grid[height - 1][0] = "─"
    for x in range(1, cols):
        y0, y1 = rows[x - 1], rows[x]
        if y0 == y1:
            grid[height - 1 - y1][x] = "─"
        else:  # a cumulative total never falls, so the line only rises here
            grid[height - 1 - y1][x] = "╭"
            grid[height - 1 - y0][x] = "╯"
            for y in range(y0 + 1, y1):
                grid[height - 1 - y][x] = "│"

    mid = (height - 1) // 2
    labels = {
        height - 1: f"{top:.1f}h",
        mid: f"{top * mid / (height - 1):.1f}h",
        0: "0h",
    }
    label_width = max(len(label) for label in labels.values())
    lines = []
    for r in range(height):
        y = height - 1 - r
        axis = "┤" if y in labels else "│"
        lines.append(f"{labels.get(y, ''):>{label_width}} {axis}" + "".join(grid[r]))
    lines.append(" " * label_width + " └" + "─" * cols)

    offset = label_width + 2

    def day_label(i: int) -> str:
        return (start + timedelta(days=max(i - 1, 0))).strftime(AXIS_DATE_FORMAT)

    first, last, middle = day_label(picks[0]), day_label(picks[-1]), day_label(picks[cols // 2])
    dates = [" "] * (offset + cols)
    last_pos = offset + cols - len(last)
    mid_pos = offset + cols // 2 - len(middle) // 2
    texts = [(offset, first), (last_pos, last)]
    if offset + len(first) < mid_pos and mid_pos + len(middle) < last_pos:
        texts.append((mid_pos, middle))
    for pos, text in texts:
        dates[pos : pos + len(text)] = list(text)
    lines.append("".join(dates).rstrip())

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": len(series) - 1,
        "total_hours": round(total, 2),
        "caption": (
            f"Hours studied, {start.strftime(CAPTION_DATE_FORMAT)} to "
            f"{end.strftime(CAPTION_DATE_FORMAT)} ({len(series) - 1} days)"
        ),
        "lines": [line.rstrip() for line in lines],
    }


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
