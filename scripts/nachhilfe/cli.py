"""Single entrypoint for the nachhilfebot Python backend.

Usage: python3 -m nachhilfe <command> [args...]

Skills invoke this via the Bash tool and must never read/write the JSON
databases directly. Every command prints JSON (except `status`, which
prints a formatted plain-text report) so a skill never has to reconstruct
numbers itself.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import uuid
from datetime import date, datetime
from pathlib import Path

from . import db, progress
from .fsrs import Card, RATING_NAMES
from .fsrs import review as fsrs_review


def _is_inside_git_repo(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (OSError, subprocess.SubprocessError):
        return False


def _print(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def cmd_init(args: argparse.Namespace) -> None:
    base_dir = Path.cwd()
    already_configured = (base_dir / "nachhilfe").exists()
    data_dir = db.set_data_root(base_dir)

    lang = args.target_language
    db.init_language(lang)

    hours_table = db.load_db("level-hours", lang)["transitions"]
    hours_needed = progress.hours_between(args.current_level, args.aim_level, hours_table)
    days_available = (date.fromisoformat(args.target_date) - date.today()).days
    minutes_per_day = progress.daily_minutes_target(hours_needed, days_available)

    profile = {
        "schema_version": db.SCHEMA_VERSION,
        "native_languages": [x.strip() for x in args.native.split(",") if x.strip()],
        "target_language": lang,
        "current_level": args.current_level,
        "aim_level": args.aim_level,
        "target_date": args.target_date,
        "created_at": date.today().isoformat(),
        "hours_needed_total": hours_needed,
        "daily_minutes_target": round(minutes_per_day),
    }
    db.save_db("profile", profile, lang)

    config = db.load_config()
    config["active_language"] = lang
    db.save_config(config)

    profile["data_dir"] = str(data_dir)
    profile["data_dir_already_configured"] = already_configured
    profile["data_dir_in_git_repo"] = _is_inside_git_repo(data_dir.parent)

    _print(profile)


def cmd_status(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    profile = db.load_db("profile", lang)
    status = db.load_db("status", lang)
    vocab = db.load_db("vocab", lang)
    grammar = db.load_db("grammar", lang)
    hours_table = db.load_db("level-hours", lang)["transitions"]
    thresholds = db.load_db("mastery-thresholds", lang)

    sessions = status["sessions"]
    today = date.today()

    hours_needed = progress.hours_between(profile["current_level"], profile["aim_level"], hours_table)
    done = progress.hours_done(sessions)

    report = {
        "profile": profile,
        "progress": {
            "hours_done": round(done, 2),
            "hours_needed": hours_needed,
            "hours_left": round(max(hours_needed - done, 0), 2),
            "bar": progress.progress_bar(done, hours_needed),
        },
        "streak": progress.compute_streak(sessions, today),
        "last_sessions": progress.last_n_sessions(sessions, 10),
        "active_days": progress.active_days_table(sessions, 10),
        "vocab_mastery": progress.mastery_breakdown(
            vocab["cards"], thresholds["very_good_stability_days"], thresholds["good_stability_days"]
        ),
        "mastery_thresholds": thresholds,
        "reading": {
            "average_last_5": progress.rolling_average(sessions, "reading", 5),
            "history": progress.score_history_table(sessions, "reading"),
        },
        "writing": {
            "average_last_5": progress.rolling_average(sessions, "writing", 5),
            "history": progress.score_history_table(sessions, "writing"),
        },
        "grammar": {
            "average_last_5": progress.rolling_average(sessions, "grammar", 5),
            "history": progress.score_history_table(sessions, "grammar"),
            "weak_topics": progress.weak_grammar_topics(grammar.get("mistake_counts", {})),
        },
    }
    _print(report)


def cmd_session_start_banner(args: argparse.Namespace) -> None:
    config = db.load_config()
    lang = config.get("active_language")
    if not lang:
        print("[nachhilfebot] No learner profile yet. Run /nachhilfe-init to get started.")
        return

    profile = db.load_db("profile", lang)
    status = db.load_db("status", lang)
    vocab = db.load_db("vocab", lang)
    today = date.today()

    streak = progress.compute_streak(status["sessions"], today)
    due = sum(
        1
        for c in vocab["cards"]
        if c["state"] == "new" or (c.get("due") and date.fromisoformat(c["due"]) <= today)
    )

    lines = [
        f"[nachhilfebot] Learning: {profile['target_language']} "
        f"({profile['current_level']} -> {profile['aim_level']})",
        f"Streak: {streak['current']} day(s)",
    ]
    if due:
        lines.append(f"{due} vocab card(s) due today - run /nachhilfe-vocab!")
    print("\n".join(lines))


def cmd_paths(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    lang_dir = db.lang_dir(lang)
    _print(
        {
            "lang_dir": str(lang_dir),
            "custom_prompts": str(lang_dir / "CUSTOM_PROMPTS.md"),
        }
    )


def cmd_vocab_words(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    vocab = db.load_db("vocab", lang)
    _print(sorted({c["native_word"] for c in vocab["cards"]}))


def cmd_vocab_reveal(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    vocab = db.load_db("vocab", lang)
    for c in vocab["cards"]:
        if c["id"] == args.card_id:
            _print({"id": c["id"], "native_word": c["native_word"], "target_word": c["target_word"]})
            return
    raise SystemExit(f"No such card id: {args.card_id}")


def cmd_vocab_due(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    vocab = db.load_db("vocab", lang)
    today = date.today()
    due = [
        c
        for c in vocab["cards"]
        if c["state"] == "new" or (c.get("due") and date.fromisoformat(c["due"]) <= today)
    ]
    due.sort(key=lambda c: (c["state"] != "new", c.get("due") or ""))
    _print([{"id": c["id"], "native_word": c["native_word"], "level": c.get("level")} for c in due[: args.limit]])


def cmd_vocab_add(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    vocab = db.load_db("vocab", lang)
    card = {
        "id": str(uuid.uuid4())[:8],
        "native_word": args.native_word,
        "target_word": args.target_word,
        "level": args.level,
        "state": "new",
        "difficulty": None,
        "stability": None,
        "reps": 0,
        "lapses": 0,
        "last_review": None,
        "due": None,
        "created_at": date.today().isoformat(),
    }
    vocab["cards"].append(card)
    db.save_db("vocab", vocab, lang)
    _print(card)


def cmd_vocab_review(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    vocab = db.load_db("vocab", lang)
    today = date.today()

    for c in vocab["cards"]:
        if c["id"] != args.card_id:
            continue
        card = Card(
            difficulty=c["difficulty"],
            stability=c["stability"],
            reps=c["reps"],
            lapses=c["lapses"],
            last_review=date.fromisoformat(c["last_review"]) if c["last_review"] else None,
            due=date.fromisoformat(c["due"]) if c["due"] else None,
            state=c["state"],
        )
        fsrs_review(card, RATING_NAMES[args.rating], today)
        c.update(
            {
                "difficulty": round(card.difficulty, 4),
                "stability": round(card.stability, 4),
                "reps": card.reps,
                "lapses": card.lapses,
                "last_review": card.last_review.isoformat(),
                "due": card.due.isoformat(),
                "state": card.state,
            }
        )
        db.save_db("vocab", vocab, lang)
        _print(c)
        return
    raise SystemExit(f"No such card id: {args.card_id}")


def cmd_session_log(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    status = db.load_db("status", lang)
    session = {
        "id": str(uuid.uuid4())[:8],
        "date": args.date or date.today().isoformat(),
        "logged_at": datetime.now().isoformat(timespec="seconds"),
        "type": args.type,
        "minutes": args.minutes,
        "score": args.score,
        "topic": args.topic,
        "mistakes": args.mistake or [],
    }
    status["sessions"].append(session)
    db.save_db("status", status, lang)

    if session["mistakes"]:
        grammar = db.load_db("grammar", lang)
        counts = grammar.setdefault("mistake_counts", {})
        for topic in session["mistakes"]:
            counts[topic] = counts.get(topic, 0) + 1
        db.save_db("grammar", grammar, lang)

    _print(session)


def cmd_grammar_topics(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    grammar = db.load_db("grammar", lang)
    profile = db.load_db("profile", lang)
    level = args.level or profile["current_level"]
    _print(grammar.get("topics", {}).get(level, []))


def cmd_grammar_weak(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    grammar = db.load_db("grammar", lang)
    _print(progress.weak_grammar_topics(grammar.get("mistake_counts", {}), args.limit))


def cmd_config_get(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    _print(db.load_db(args.file, lang))


def cmd_config_set_hours(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    data = db.load_db("level-hours", lang)
    data["transitions"][args.transition] = args.hours
    db.save_db("level-hours", data, lang)
    _print(data)


def cmd_config_set_threshold(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    data = db.load_db("mastery-thresholds", lang)
    data[args.key] = args.value
    db.save_db("mastery-thresholds", data, lang)
    _print(data)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nachhilfe")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a learner profile and DB files")
    p.add_argument("--native", required=True, help="comma-separated native language(s)")
    p.add_argument("--target-language", required=True, help="e.g. de")
    p.add_argument("--current-level", required=True, choices=progress.LEVELS)
    p.add_argument("--aim-level", required=True, choices=progress.LEVELS)
    p.add_argument("--target-date", required=True, help="YYYY-MM-DD")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("status", help="full status report as JSON")
    p.add_argument("--lang")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("session-start-banner", help="one-line SessionStart hook banner")
    p.set_defaults(func=cmd_session_start_banner)

    p = sub.add_parser("paths", help="resolve the active language's data directory")
    p.add_argument("--lang")
    p.set_defaults(func=cmd_paths)

    p = sub.add_parser("vocab-words", help="existing native-language words, for duplicate avoidance")
    p.add_argument("--lang")
    p.set_defaults(func=cmd_vocab_words)

    p = sub.add_parser("vocab-reveal", help="reveal a card's correct answer, for grading")
    p.add_argument("--lang")
    p.add_argument("--card-id", required=True)
    p.set_defaults(func=cmd_vocab_reveal)

    p = sub.add_parser("vocab-due", help="cards due for review")
    p.add_argument("--lang")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_vocab_due)

    p = sub.add_parser("vocab-add", help="add a new vocab card")
    p.add_argument("--lang")
    p.add_argument("--native-word", required=True)
    p.add_argument("--target-word", required=True)
    p.add_argument("--level", required=True, choices=progress.LEVELS)
    p.set_defaults(func=cmd_vocab_add)

    p = sub.add_parser("vocab-review", help="apply an FSRS rating to a card")
    p.add_argument("--lang")
    p.add_argument("--card-id", required=True)
    p.add_argument("--rating", required=True, choices=list(RATING_NAMES))
    p.set_defaults(func=cmd_vocab_review)

    p = sub.add_parser("session-log", help="log a completed session")
    p.add_argument("--lang")
    p.add_argument("--type", required=True, choices=["vocab", "writing", "reading", "grammar"])
    p.add_argument("--minutes", type=int, required=True)
    p.add_argument("--score", type=float)
    p.add_argument("--topic")
    p.add_argument(
        "--mistake",
        action="append",
        help="a grammar topic tag (exact string from grammar-topics); repeat for multiple",
    )
    p.add_argument("--date")
    p.set_defaults(func=cmd_session_log)

    p = sub.add_parser("grammar-topics", help="taxonomy for a level")
    p.add_argument("--lang")
    p.add_argument("--level", choices=progress.LEVELS)
    p.set_defaults(func=cmd_grammar_topics)

    p = sub.add_parser("grammar-weak", help="topics with the most tagged mistakes")
    p.add_argument("--lang")
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=cmd_grammar_weak)

    p = sub.add_parser("config-get", help="read a config file")
    p.add_argument("--lang")
    p.add_argument("--file", required=True, choices=["level-hours", "mastery-thresholds", "profile"])
    p.set_defaults(func=cmd_config_get)

    p = sub.add_parser("config-set-hours", help="override hours for one level transition")
    p.add_argument("--lang")
    p.add_argument("--transition", required=True, help='e.g. "B1->B2"')
    p.add_argument("--hours", type=float, required=True)
    p.set_defaults(func=cmd_config_set_hours)

    p = sub.add_parser("config-set-threshold", help="override an FSRS mastery threshold")
    p.add_argument("--lang")
    p.add_argument("--key", required=True, choices=["very_good_stability_days", "good_stability_days"])
    p.add_argument("--value", type=float, required=True)
    p.set_defaults(func=cmd_config_set_threshold)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
