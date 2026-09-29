from datetime import date, timedelta

from nachhilfe import progress

HOURS_TABLE = {
    "0->A1": 100,
    "A1->A2": 100,
    "A2->B1": 180,
    "B1->B2": 180,
    "B2->C1": 200,
    "C1->C2": 200,
}


def test_hours_between_sums_intermediate_transitions():
    assert progress.hours_between("B1", "C1", HOURS_TABLE) == 380


def test_hours_between_same_level_is_zero():
    assert progress.hours_between("A1", "A1", HOURS_TABLE) == 0.0


def test_hours_between_aim_below_current_is_zero():
    assert progress.hours_between("C1", "A1", HOURS_TABLE) == 0.0


def test_daily_minutes_target_assumes_one_rest_day_per_week():
    minutes = progress.daily_minutes_target(hours_needed=100, days_available=100)
    expected = (100 * 60) / (100 * 6 / 7)
    assert round(minutes, 4) == round(expected, 4)


def test_daily_minutes_target_zero_days_available():
    assert progress.daily_minutes_target(100, 0) == 0.0


def test_progress_bar_extremes_and_midpoint():
    assert progress.progress_bar(0, 100, width=10) == "[" + "-" * 10 + "]"
    assert progress.progress_bar(100, 100, width=10) == "[" + "#" * 10 + "]"
    assert progress.progress_bar(50, 100, width=10) == "[" + "#" * 5 + "-" * 5 + "]"


def test_progress_bar_zero_target_is_treated_as_fully_done():
    assert progress.progress_bar(5, 0, width=10) == "[" + "#" * 10 + "]"


def test_compute_streak_all_consecutive_days_including_today():
    today = date(2026, 1, 10)
    sessions = [{"date": (today - timedelta(days=i)).isoformat()} for i in range(5)]
    streak = progress.compute_streak(sessions, today)
    assert streak == {"current": 5, "longest": 5, "last_active_date": today.isoformat()}


def test_compute_streak_broken_by_a_gap_day():
    today = date(2026, 1, 10)
    dates = [today, today - timedelta(days=1), today - timedelta(days=3)]  # day 2 skipped
    sessions = [{"date": d.isoformat()} for d in dates]
    streak = progress.compute_streak(sessions, today)
    assert streak["current"] == 2
    assert streak["longest"] == 2


def test_compute_streak_no_session_yet_today_still_counts_yesterday():
    today = date(2026, 1, 10)
    sessions = [{"date": (today - timedelta(days=1)).isoformat()}]
    streak = progress.compute_streak(sessions, today)
    assert streak["current"] == 1


def test_compute_streak_broken_once_a_full_day_was_skipped():
    today = date(2026, 1, 10)
    sessions = [{"date": (today - timedelta(days=2)).isoformat()}]
    streak = progress.compute_streak(sessions, today)
    assert streak["current"] == 0


def test_compute_streak_with_no_sessions_at_all():
    assert progress.compute_streak([], date(2026, 1, 10)) == {
        "current": 0,
        "longest": 0,
        "last_active_date": None,
    }


def test_active_days_table_aggregates_count_and_minutes_per_day():
    sessions = [
        {"date": "2026-01-01", "minutes": 10},
        {"date": "2026-01-01", "minutes": 15},
        {"date": "2026-01-02", "minutes": 20},
    ]
    table = {row["date"]: row for row in progress.active_days_table(sessions, n=10)}
    assert table["2026-01-01"] == {"date": "2026-01-01", "count": 2, "minutes": 25}
    assert table["2026-01-02"] == {"date": "2026-01-02", "count": 1, "minutes": 20}


def test_active_days_table_respects_limit_and_most_recent_first():
    sessions = [{"date": f"2026-01-{d:02d}", "minutes": 5} for d in range(1, 15)]
    table = progress.active_days_table(sessions, n=5)
    assert len(table) == 5
    assert table[0]["date"] == "2026-01-14"


def test_last_n_sessions_limits_and_orders_most_recent_first():
    sessions = [{"date": f"2026-01-{d:02d}", "id": str(d)} for d in range(1, 15)]
    last = progress.last_n_sessions(sessions, n=3)
    assert [s["id"] for s in last] == ["14", "13", "12"]


def test_last_n_sessions_orders_same_day_by_logged_at_then_file_order():
    sessions = [
        {"date": "2026-01-01", "id": "zzz"},  # legacy, no logged_at, oldest
        {"date": "2026-01-01", "id": "aaa"},  # legacy, later in file
        {"date": "2026-01-01", "id": "mmm", "logged_at": "2026-01-01T09:00:00"},
        {"date": "2026-01-01", "id": "bbb", "logged_at": "2026-01-01T18:30:00"},
    ]
    last = progress.last_n_sessions(sessions, n=4)
    assert [s["id"] for s in last] == ["bbb", "mmm", "aaa", "zzz"]


def test_mastery_breakdown_buckets_cards_correctly():
    cards = [
        {"state": "new"},
        {"state": "review", "stability": 25},
        {"state": "review", "stability": 10},
        {"state": "review", "stability": 3},
        {"state": "review", "stability": None},
    ]
    counts = progress.mastery_breakdown(cards, very_good_days=21, good_days=7)
    assert counts == {"very_good": 1, "good": 1, "in_learning": 3}


def test_rolling_average_ignores_unscored_sessions_and_other_types():
    sessions = [
        {"type": "writing", "date": "2026-01-01", "score": 5},
        {"type": "writing", "date": "2026-01-02", "score": 7},
        {"type": "writing", "date": "2026-01-03", "score": None},
        {"type": "reading", "date": "2026-01-01", "score": 90},
    ]
    assert progress.rolling_average(sessions, "writing", n=5) == 6
    assert progress.rolling_average(sessions, "grammar", n=5) is None


def test_rolling_average_only_uses_last_n():
    sessions = [{"type": "writing", "date": f"2026-01-{d:02d}", "score": d} for d in range(1, 8)]
    # last 3 scores are 5, 6, 7 -> average 6
    assert progress.rolling_average(sessions, "writing", n=3) == 6


def test_score_history_table_is_per_session_at_or_below_ten():
    sessions = [{"type": "writing", "date": f"2026-01-{d:02d}", "score": d} for d in range(1, 6)]
    history = progress.score_history_table(sessions, "writing")
    assert history == [{"period": f"2026-01-{d:02d}", "score": d} for d in range(1, 6)]


def test_score_history_table_rolls_up_to_weeks_once_past_ten():
    monday = date(2026, 1, 5) - timedelta(days=date(2026, 1, 5).weekday())
    week1 = [monday + timedelta(days=i) for i in range(5)]  # Mon-Fri
    week2 = [monday + timedelta(days=7 + i) for i in range(6)]  # next Mon-Sat
    sessions = [
        {"type": "writing", "date": d.isoformat(), "score": 5} for d in week1 + week2
    ]
    assert len(sessions) == 11  # past the <=10 per-session cutoff

    history = progress.score_history_table(sessions, "writing")
    assert len(history) == 2
    assert all("W" in row["period"] for row in history)


def test_weak_grammar_topics_sorted_descending_and_limited():
    counts = {"A": 5, "B": 2, "C": 9, "D": 1}
    assert progress.weak_grammar_topics(counts, limit=2) == [["C", 9], ["A", 5]]


def test_weak_grammar_topics_empty_when_no_mistakes():
    assert progress.weak_grammar_topics({}) == []
