"""Deterministic core of /nachhilfe-dialog.

The learner practises real-life conversations: the model plays the other
person, the learner answers (short and direct, like in real life) and may ask
questions too. The model invents every dialog from scratch - the situation,
the people, their mood and the unexpected turn - so there is no fixed
scenario list. The code only does what the model is bad at:

* a random nudge (a broad area of life) per dialog, because left alone a
  model drifts to the same few situations;
* a memory of the situations played lately, so the model does not repeat them;
* whether a surprise happens and after which answer;
* the grade of every answer, computed from three sub-scores, and the session
  average.
"""
from __future__ import annotations

import random

DEFAULT_TURNS = 8  # learner answers per dialog
RECENT_MEMORY = 20  # situation titles the model is shown, to avoid repeating them
SURPRISE_CHANCE = 0.7

# Sub-scores of one answer; their sum is the grade out of 10 (see RUBRIC.md).
FIT_MAX, ACCURACY_MAX, NATURAL_MAX = 4, 3, 3

# Broad areas of everyday life: a nudge only, the model invents the concrete situation.
DOMAINS = [
    "shopping and money", "food and eating out", "health and the body",
    "housing and neighbours", "travel and transport", "work and colleagues",
    "job hunting and career", "authorities and paperwork", "school, courses and learning",
    "family and children", "friends and social life", "free time, sport and hobbies",
    "technology and the internet", "phone calls and customer service", "repairs and technical problems",
    "cars, bikes and mobility", "weather, nature and animals", "events, parties and celebrations",
    "news, politics and opinions", "misunderstandings and complaints",
    "an emergency or something going wrong", "meeting someone new", "banks, insurance and contracts",
    "culture, cinema and going out",
]


def build_session(
    level: str,
    recent_titles: list[str],
    rng: random.Random,
    turns: int = DEFAULT_TURNS,
    request: str | None = None,
) -> dict:
    """Plan one dialog. The situation itself is registered later by the model."""
    surprise_after = None
    if turns >= 4 and rng.random() < SURPRISE_CHANCE:
        surprise_after = rng.randint(2, turns - 2)
    return {
        "level": level,
        "domain": None if request else rng.choice(DOMAINS),
        "request": request,
        "recent_titles": recent_titles[-RECENT_MEMORY:],
        "turns": turns,
        "surprise_after_turn": surprise_after,
        "scenario": None,
        "results": [],
    }


def turn_score(fit: int, accuracy: int, natural: int) -> int:
    return fit + accuracy + natural


def check_subscores(fit: int, accuracy: int, natural: int) -> str | None:
    """None when the sub-scores are within range, else what is wrong."""
    for name, value, top in (
        ("fit", fit, FIT_MAX), ("accuracy", accuracy, ACCURACY_MAX), ("natural", natural, NATURAL_MAX),
    ):
        if not 0 <= value <= top:
            return f"--{name} must be between 0 and {top}."
    return None
