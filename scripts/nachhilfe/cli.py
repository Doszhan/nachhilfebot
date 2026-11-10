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
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

from . import db, progress, retry, translate
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


def _is_due(card: dict, today: date) -> bool:
    """Due today (or never reviewed), and not hidden with `vocab-suppress`."""
    if card.get("suppressed"):
        return False
    return card["state"] == "new" or bool(card.get("due") and date.fromisoformat(card["due"]) <= today)


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
        "translate": {
            "average_last_5": progress.rolling_average(sessions, "translate", 5),
            "history": progress.score_history_table(sessions, "translate"),
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
    due = sum(1 for c in vocab["cards"] if _is_due(c, today))

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
    due = [c for c in vocab["cards"] if _is_due(c, today)]
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
        was_learned = card.state != "new"
        fsrs_review(card, RATING_NAMES[args.rating], today)
        if args.rating == "hard" and was_learned:
            # Same rule as `again` (a first look is never a lapse). Scheduling is
            # untouched: fsrs.py never reads `lapses`; the counter just also
            # records "right, but with a real error", so such words show up as weak.
            card.lapses += 1
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

        if args.rating in retry.RETRY_RATINGS:
            state = db.load_optional(retry.STATE_NAME, retry.empty_state(today), lang)
            state = retry.record_failure(state, c["id"], args.rating, today)
            db.save_db(retry.STATE_NAME, state, lang)

        _print(c)
        return
    raise SystemExit(f"No such card id: {args.card_id}")


def cmd_vocab_retry_list(args: argparse.Namespace) -> None:
    """Cards rated again/hard in today's session that still need a retry.

    Only the native-language side is returned, like `vocab-due`.
    """
    lang = args.lang or db.active_language()
    vocab = db.load_db("vocab", lang)
    today = date.today()
    state = db.load_optional(retry.STATE_NAME, retry.empty_state(today), lang)
    by_id = {c["id"]: c for c in vocab["cards"]}
    pending = [
        {
            "id": row["id"],
            "native_word": by_id[row["id"]]["native_word"],
            "level": by_id[row["id"]].get("level"),
            "rating": row["rating"],
            "attempts": row["attempts"],
        }
        for row in retry.pending(state, today, args.max_attempts)
        if row["id"] in by_id
    ]
    _print({**retry.counts(state, today), "pending": pending})


def cmd_vocab_retry_record(args: argparse.Namespace) -> None:
    """Record the outcome of one retry question. Never touches FSRS state."""
    lang = args.lang or db.active_language()
    today = date.today()
    state = db.load_optional(retry.STATE_NAME, retry.empty_state(today), lang)
    try:
        state = retry.record_attempt(state, args.card_id, args.result == "correct", today)
    except KeyError:
        raise SystemExit(f"Card {args.card_id} is not in today's retry list.")
    db.save_db(retry.STATE_NAME, state, lang)
    entry = state["failed"][args.card_id]
    _print(
        {
            "card_id": args.card_id,
            "attempts": entry["attempts"],
            "fixed": entry["fixed"],
            "remaining": len(retry.pending(state, today, args.max_attempts)),
        }
    )


def cmd_vocab_suppress(args: argparse.Namespace) -> None:
    """Hide a flawed or duplicate card from review and translate practice."""
    lang = args.lang or db.active_language()
    vocab = db.load_db("vocab", lang)
    for c in vocab["cards"]:
        if c["id"] == args.card_id:
            if args.undo:
                c.pop("suppressed", None)
            else:
                c["suppressed"] = True
            db.save_db("vocab", vocab, lang)
            _print(c)
            return
    raise SystemExit(f"No such card id: {args.card_id}")


def _append_session(
    lang: str,
    session_type: str,
    minutes: int,
    score: float | None,
    topic: str | None,
    mistakes: list[str],
    session_date: str | None = None,
) -> dict:
    """Append to the session log and fold grammar mistake tags into the counts."""
    status = db.load_db("status", lang)
    session = {
        "id": str(uuid.uuid4())[:8],
        "date": session_date or date.today().isoformat(),
        "logged_at": datetime.now().isoformat(timespec="seconds"),
        "type": session_type,
        "minutes": minutes,
        "score": score,
        "topic": topic,
        "mistakes": mistakes,
    }
    status["sessions"].append(session)
    db.save_db("status", status, lang)

    if mistakes:
        grammar = db.load_db("grammar", lang)
        counts = grammar.setdefault("mistake_counts", {})
        for tag in mistakes:
            counts[tag] = counts.get(tag, 0) + 1
        db.save_db("grammar", grammar, lang)
    return session


def cmd_session_log(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    session = _append_session(
        lang, args.type, args.minutes, args.score, args.topic, args.mistake or [], args.date
    )
    if args.type == "vocab":
        db.delete_db(retry.STATE_NAME, lang)  # the retry list belongs to this session
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


# ---------------------------------------------------------------- translate

TRANSLATE_DB = "translate"
TRANSLATE_SESSION = "translate-session"
_TRANSLATE_DEFAULT = {"schema_version": 1, "settings": {}, "cards": {}}


def _translate_state(lang: str) -> dict:
    return db.load_optional(TRANSLATE_DB, _TRANSLATE_DEFAULT, lang)


def _open_translate_session(lang: str) -> dict:
    session = db.load_optional(TRANSLATE_SESSION, {}, lang)
    if not session:
        raise SystemExit("No translate session is open. Run translate-start first.")
    return session


def _all_grammar_topics(grammar: dict) -> set[str]:
    return {t for topics in grammar.get("topics", {}).values() for t in topics}


def _read_stdin_or(value: str | None, what: str) -> str:
    text = value if value is not None else sys.stdin.read()
    if not text.strip():
        raise SystemExit(f"Empty {what}.")
    return text


def cmd_translate_config(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    profile = db.load_db("profile", lang)
    state = _translate_state(lang)
    if args.source_language:
        state["settings"]["source_language"] = args.source_language
        db.save_db(TRANSLATE_DB, state, lang)
    _print(
        {
            "source_language": state["settings"].get("source_language"),
            "default_source_language": profile["native_languages"][0],
            "native_languages": profile["native_languages"],
        }
    )


def cmd_translate_start(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    today = date.today()

    existing = db.load_optional(TRANSLATE_SESSION, {}, lang)
    if existing and existing.get("date") == today.isoformat() and not (args.new or args.preview):
        _print(
            {
                "resumed": True,
                "source_language": existing["source_language"],
                "level": existing["level"],
                "slots": existing["slots"],
                "sentences_submitted": bool(existing.get("sentences")),
                "recorded": sorted(int(n) for n in existing.get("results", {})),
            }
        )
        return

    profile = db.load_db("profile", lang)
    vocab = db.load_db("vocab", lang)
    grammar = db.load_db("grammar", lang)
    state = _translate_state(lang)
    level = profile["current_level"]
    source_language = (
        args.source_language
        or state["settings"].get("source_language")
        or profile["native_languages"][0]
    )
    try:
        slots = translate.build_slots(
            vocab["cards"],
            state["cards"],
            grammar.get("mistake_counts", {}),
            grammar.get("topics", {}).get(level, []),
            lang,
            today,
            count=args.count,
            per_sentence=args.per_sentence,
            seed=args.seed,
        )
    except ValueError as err:
        raise SystemExit(str(err))

    session = {
        "schema_version": 1,
        "date": today.isoformat(),
        "source_language": source_language,
        "level": level,
        "slots": slots,
        "sentences": {},
        "answers": {},
        "checks": {},
        "results": {},
    }
    if not args.preview:
        db.save_db(TRANSLATE_SESSION, session, lang)
    _print(
        {
            "resumed": False,
            "preview": args.preview,
            "source_language": source_language,
            "level": level,
            "slots": slots,
        }
    )


def cmd_translate_submit(args: argparse.Namespace) -> None:
    """The model hands in the sentences it wrote (JSON on stdin); code validates them."""
    lang = args.lang or db.active_language()
    session = _open_translate_session(lang)
    if session.get("answers"):
        raise SystemExit("Answers were already collected; sentences can no longer be replaced.")
    try:
        submitted = json.loads(_read_stdin_or(args.json, "submission"))
    except json.JSONDecodeError as err:
        raise SystemExit(f"Submission is not valid JSON: {err}")

    errors = translate.validate_submission(session["slots"], submitted, lang)
    if errors:
        raise SystemExit("Sentences rejected - fix and resubmit all of them:\n- " + "\n- ".join(errors))

    session["sentences"] = {
        str(item["n"]): {
            "source": item["source"].strip(),
            "reference": item["reference"].strip(),
            "keys": [
                {"card_id": k["card_id"], "tokens": translate.key_tokens(k)} for k in item["keys"]
            ],
        }
        for item in submitted
    }
    db.save_db(TRANSLATE_SESSION, session, lang)
    _print({"accepted": len(session["sentences"])})


def cmd_translate_next(args: argparse.Namespace) -> None:
    """The next sentence to show the learner: only the source text, never the reference."""
    lang = args.lang or db.active_language()
    session = _open_translate_session(lang)
    if not session.get("sentences"):
        raise SystemExit("No sentences submitted yet. Run translate-submit first.")
    total = len(session["slots"])
    answered = len(session["results"])
    for slot in session["slots"]:
        n = str(slot["n"])
        if n not in session["results"]:
            _print(
                {
                    "done": False,
                    "n": slot["n"],
                    "total": total,
                    "answered": answered,
                    "source": session["sentences"][n]["source"],
                    "already_checked": n in session["checks"],
                }
            )
            return
    _print({"done": True, "total": total, "answered": answered})


def cmd_translate_check(args: argparse.Namespace) -> None:
    lang = args.lang or db.active_language()
    session = _open_translate_session(lang)
    n = str(args.n)
    if n not in session.get("sentences", {}):
        raise SystemExit(f"No sentence {n} in this session.")
    if n in session["results"]:
        raise SystemExit(f"Sentence {n} already has a verdict.")
    answer = _read_stdin_or(args.answer, "answer").strip()

    slot = next(s for s in session["slots"] if str(s["n"]) == n)
    sentence = session["sentences"][n]
    result = translate.check_answer(answer, sentence, slot["grammar_topic"], lang)
    session["answers"][n] = answer
    session["checks"][n] = result
    if result["exact_match"]:
        session["results"][n] = {"verdict": "correct", "mistakes": [], "accepted": [], "auto": True}
    db.save_db(TRANSLATE_SESSION, session, lang)
    _print(
        {
            "n": args.n,
            "reference": sentence["reference"],
            "grammar_topic": slot["grammar_topic"],
            **result,
            "verdict_recorded": result["exact_match"],
        }
    )


def cmd_translate_record(args: argparse.Namespace) -> None:
    """Store the model's verdict for one sentence, within the code's guard rails."""
    lang = args.lang or db.active_language()
    session = _open_translate_session(lang)
    n = str(args.n)
    if n not in session["checks"]:
        raise SystemExit(f"Run translate-check for sentence {n} first.")
    if n in session["results"]:
        raise SystemExit(f"Sentence {n} already has a verdict.")

    grammar = db.load_db("grammar", lang)
    known = _all_grammar_topics(grammar)
    mistakes = args.mistake or []
    unknown = [m for m in mistakes if m not in known]
    if unknown:
        raise SystemExit(
            f"Unknown grammar topic tag(s): {unknown}. Use the exact strings from grammar-topics."
        )

    slot = next(s for s in session["slots"] if str(s["n"]) == n)
    slot_ids = {c["id"] for c in slot["cards"]}
    accepted = set(args.accept or [])
    if not accepted <= slot_ids:
        raise SystemExit(f"--accept ids must be target cards of sentence {n}: {sorted(slot_ids)}")

    if args.verdict == "correct":
        if mistakes:
            raise SystemExit("A 'correct' verdict cannot carry mistake tags.")
        unresolved = [
            k["card_id"]
            for k in session["checks"][n]["keys"]
            if k["verdict"] != "ok" and k["card_id"] not in accepted
        ]
        if unresolved:
            raise SystemExit(
                f"Target word(s) {unresolved} were missing or misspelled in the answer, so "
                "'correct' is not allowed. Use 'partial'/'wrong', or pass --accept <card_id> "
                "if the learner used an equally valid expression."
            )

    session["results"][n] = {
        "verdict": args.verdict,
        "mistakes": mistakes,
        "accepted": sorted(accepted),
        "auto": False,
    }
    db.save_db(TRANSLATE_SESSION, session, lang)
    _print({"n": args.n, "verdict": args.verdict, "answered": len(session["results"])})


def cmd_translate_finish(args: argparse.Namespace) -> None:
    """Score the session, update per-word stats, log it, and close it."""
    lang = args.lang or db.active_language()
    today = date.today()
    session = _open_translate_session(lang)
    results = session["results"]
    open_ns = [s["n"] for s in session["slots"] if str(s["n"]) not in results]
    if open_ns and not args.allow_partial:
        raise SystemExit(
            f"Sentences without a verdict: {open_ns}. Finish them, or pass --allow-partial."
        )
    if not results:
        raise SystemExit("Nothing was answered; nothing to log.")

    answered = [s for s in session["slots"] if str(s["n"]) in results]
    verdicts = [results[str(s["n"])]["verdict"] for s in answered]
    score = translate.score_out_of_10(verdicts)

    vocab = db.load_db("vocab", lang)
    by_id = {c["id"]: c for c in vocab["cards"]}
    state = _translate_state(lang)
    hit, missed, spelling = [], [], []
    marker_missing: list[str] = []
    mistakes: list[str] = []
    for slot in answered:
        n = str(slot["n"])
        result = results[n]
        check = session["checks"][n]
        mistakes.extend(result["mistakes"])
        if check["grammar_marker_found"] is False and slot["grammar_topic"]:
            marker_missing.append(slot["grammar_topic"])
        for key in check["keys"]:
            outcome = translate.card_outcome(key, set(result["accepted"]))
            translate.update_stats(state["cards"], key["card_id"], outcome, today)
            entry = {"id": key["card_id"], "target_word": by_id[key["card_id"]]["target_word"], "n": slot["n"]}
            {"hit": hit, "spelling": spelling, "miss": missed}[outcome].append(entry)
    db.save_db(TRANSLATE_DB, state, lang)

    logged = _append_session(
        lang,
        "translate",
        args.minutes,
        score,
        f"Translation ({session['source_language']} -> {lang})",
        mistakes,
    )
    db.delete_db(TRANSLATE_SESSION, lang)
    _print(
        {
            "session": logged,
            "score": score,
            "answered": len(answered),
            "total": len(session["slots"]),
            "correct": verdicts.count("correct"),
            "partial": verdicts.count("partial"),
            "wrong": verdicts.count("wrong"),
            "vocab_missed": missed,
            "vocab_spelling": spelling,
            "vocab_hit": hit,
            "grammar_mistakes": [[t, mistakes.count(t)] for t in sorted(set(mistakes), key=lambda t: (-mistakes.count(t), t))],
            "construction_possibly_avoided": sorted(set(marker_missing)),
        }
    )


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

    p = sub.add_parser(
        "vocab-retry-list",
        help="cards rated again/hard in today's session that still need a retry (no FSRS)",
    )
    p.add_argument("--lang")
    p.add_argument("--max-attempts", type=int, default=retry.DEFAULT_MAX_ATTEMPTS)
    p.set_defaults(func=cmd_vocab_retry_list)

    p = sub.add_parser(
        "vocab-retry-record", help="record one retry answer; never changes FSRS state"
    )
    p.add_argument("--lang")
    p.add_argument("--card-id", required=True)
    p.add_argument("--result", required=True, choices=["correct", "wrong"])
    p.add_argument("--max-attempts", type=int, default=retry.DEFAULT_MAX_ATTEMPTS)
    p.set_defaults(func=cmd_vocab_retry_record)

    p = sub.add_parser(
        "vocab-suppress", help="hide a flawed/duplicate card from review and translate practice"
    )
    p.add_argument("--lang")
    p.add_argument("--card-id", required=True)
    p.add_argument("--undo", action="store_true", help="make the card active again")
    p.set_defaults(func=cmd_vocab_suppress)

    p = sub.add_parser("session-log", help="log a completed session")
    p.add_argument("--lang")
    p.add_argument(
        "--type", required=True, choices=["vocab", "writing", "reading", "grammar", "translate"]
    )
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

    p = sub.add_parser("translate-config", help="show or set the translate source language")
    p.add_argument("--lang")
    p.add_argument("--source-language", help="language the sentences are written in, e.g. Russian")
    p.set_defaults(func=cmd_translate_config)

    p = sub.add_parser(
        "translate-start",
        help="plan a translate session: target words and grammar topics from your weak spots",
    )
    p.add_argument("--lang")
    p.add_argument("--count", type=int, default=translate.DEFAULT_COUNT)
    p.add_argument("--per-sentence", type=int, default=translate.DEFAULT_PER_SENTENCE)
    p.add_argument("--source-language")
    p.add_argument("--seed", type=int)
    p.add_argument("--preview", action="store_true", help="show the plan without opening a session")
    p.add_argument("--new", action="store_true", help="discard today's open session and start over")
    p.set_defaults(func=cmd_translate_start)

    p = sub.add_parser(
        "translate-submit", help="hand in the generated sentences (JSON on stdin) for validation"
    )
    p.add_argument("--lang")
    p.add_argument("--json", help="the JSON text; read from stdin when omitted")
    p.set_defaults(func=cmd_translate_submit)

    p = sub.add_parser("translate-next", help="the next source sentence to show the learner")
    p.add_argument("--lang")
    p.set_defaults(func=cmd_translate_next)

    p = sub.add_parser(
        "translate-check", help="compare the learner's answer (stdin) with the reference"
    )
    p.add_argument("--lang")
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--answer", help="the answer text; read from stdin when omitted")
    p.set_defaults(func=cmd_translate_check)

    p = sub.add_parser("translate-record", help="store the verdict for one sentence")
    p.add_argument("--lang")
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--verdict", required=True, choices=list(translate.VERDICTS))
    p.add_argument("--mistake", action="append", help="exact grammar-topic tag; repeat for several")
    p.add_argument(
        "--accept",
        action="append",
        help="card id whose word the learner replaced with an equally valid expression",
    )
    p.set_defaults(func=cmd_translate_record)

    p = sub.add_parser("translate-finish", help="score, update stats, log and close the session")
    p.add_argument("--lang")
    p.add_argument("--minutes", type=int, required=True)
    p.add_argument("--allow-partial", action="store_true")
    p.set_defaults(func=cmd_translate_finish)

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
