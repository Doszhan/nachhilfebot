"""Vendored, simplified FSRS (Free Spaced Repetition Scheduler).

A lightweight reimplementation inspired by the published FSRS algorithm (as
used in Anki / py-fsrs), trading exact upstream parity for zero external
dependencies (stdlib only). It only models long-term, day-granularity
scheduling — there is no separate same-day "learning steps" state machine,
which real FSRS has and this deliberately drops for simplicity.

Ratings: 1=Again, 2=Hard, 3=Good, 4=Easy.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

# Default weights, in the spirit of published FSRS v4 defaults. Not
# guaranteed to match any specific upstream release bit-for-bit.
DEFAULT_WEIGHTS = [
    0.40, 0.60, 2.40, 5.80,  # w0-3: initial stability by first rating
    4.93, 0.94,              # w4-5: initial difficulty
    0.86,                    # w6: difficulty delta per rating
    0.01,                    # w7: mean-reversion factor
    1.49, 0.14, 0.94,        # w8-10: recall stability growth
    2.18, 0.05, 0.34, 1.26,  # w11-14: forget (lapse) stability
    0.29, 2.61,              # w15-16: hard penalty / easy bonus
]

REQUEST_RETENTION = 0.9  # target probability of recall when a card is due
MIN_DIFFICULTY = 1.0
MAX_DIFFICULTY = 10.0
MIN_STABILITY = 0.1

Again, Hard, Good, Easy = 1, 2, 3, 4
RATING_NAMES = {"again": Again, "hard": Hard, "good": Good, "easy": Easy}


@dataclass
class Card:
    difficulty: float | None = None
    stability: float | None = None
    reps: int = 0
    lapses: int = 0
    last_review: date | None = None
    due: date | None = None
    state: str = "new"  # "new" | "review"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _init_stability(rating: int, w: list[float]) -> float:
    return max(w[rating - 1], MIN_STABILITY)


def _init_difficulty(rating: int, w: list[float]) -> float:
    return _clamp(w[4] - w[5] * (rating - 3), MIN_DIFFICULTY, MAX_DIFFICULTY)


def _next_difficulty(d: float, rating: int, w: list[float]) -> float:
    delta = -w[6] * (rating - 3)
    new_d = d + delta * (MAX_DIFFICULTY - d) / 9
    reverted = w[7] * _init_difficulty(Good, w) + (1 - w[7]) * new_d
    return _clamp(reverted, MIN_DIFFICULTY, MAX_DIFFICULTY)


def _retrievability(elapsed_days: float, stability: float) -> float:
    if stability <= 0:
        return 0.0
    return (1 + elapsed_days / (9 * stability)) ** -1


def _next_recall_stability(d: float, s: float, r: float, rating: int, w: list[float]) -> float:
    hard_penalty = w[15] if rating == Hard else 1.0
    easy_bonus = w[16] if rating == Easy else 1.0
    growth = (
        math.exp(w[8])
        * (11 - d)
        * (s ** -w[9])
        * (math.exp((1 - r) * w[10]) - 1)
        * hard_penalty
        * easy_bonus
    )
    return s * (1 + growth)


def _next_forget_stability(d: float, s: float, r: float, w: list[float]) -> float:
    return w[11] * (d ** -w[12]) * (((s + 1) ** w[13]) - 1) * math.exp((1 - r) * w[14])


def _interval_days(stability: float, retention: float = REQUEST_RETENTION) -> int:
    if stability <= 0:
        return 1
    days = 9 * stability * (1 / retention - 1)
    return max(1, round(days))


def review(card: Card, rating: int, today: date, weights: list[float] | None = None) -> Card:
    """Apply a review rating to a card in place and return it."""
    w = weights or DEFAULT_WEIGHTS
    if card.state == "new" or card.stability is None or card.difficulty is None:
        stability = _init_stability(rating, w)
        difficulty = _init_difficulty(rating, w)
    else:
        elapsed = max(0, (today - card.last_review).days) if card.last_review else 0
        r = _retrievability(elapsed, card.stability)
        difficulty = _next_difficulty(card.difficulty, rating, w)
        if rating == Again:
            stability = _next_forget_stability(card.difficulty, card.stability, r, w)
            card.lapses += 1
        else:
            stability = _next_recall_stability(card.difficulty, card.stability, r, rating, w)

    card.difficulty = difficulty
    card.stability = max(stability, MIN_STABILITY)
    card.reps += 1
    card.last_review = today
    card.due = today + timedelta(days=_interval_days(card.stability))
    card.state = "review"
    return card


def mastery_bucket(card: Card, very_good_days: float, good_days: float) -> str:
    if card.state != "review" or card.stability is None:
        return "in_learning"
    if card.stability >= very_good_days:
        return "very_good"
    if card.stability >= good_days:
        return "good"
    return "in_learning"
