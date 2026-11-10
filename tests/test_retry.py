"""Retry round: cards rated again/hard are asked once more, outside FSRS."""
import io
import json
from contextlib import redirect_stdout
from datetime import date, timedelta

import pytest

from nachhilfe import cli, db, retry

TODAY = date(2026, 11, 11)


# ---------------------------------------------------------------- pure logic

def test_record_failure_keeps_the_worse_rating():
    state = retry.empty_state(TODAY)
    state = retry.record_failure(state, "a", "hard", TODAY)
    state = retry.record_failure(state, "a", "again", TODAY)
    state = retry.record_failure(state, "a", "hard", TODAY)
    assert state["failed"]["a"]["rating"] == "again"


def test_pending_lists_again_before_hard_and_keeps_failure_order():
    state = retry.empty_state(TODAY)
    for cid, rating in [("h1", "hard"), ("a1", "again"), ("h2", "hard"), ("a2", "again")]:
        state = retry.record_failure(state, cid, rating, TODAY)
    assert [r["id"] for r in retry.pending(state, TODAY)] == ["a1", "a2", "h1", "h2"]


def test_correct_retry_removes_card_from_pending():
    state = retry.record_failure(retry.empty_state(TODAY), "a", "again", TODAY)
    state = retry.record_attempt(state, "a", True, TODAY)
    assert retry.pending(state, TODAY) == []
    assert retry.counts(state, TODAY) == {"failed": 1, "fixed": 1}


def test_wrong_retry_is_asked_again_until_attempts_run_out():
    state = retry.record_failure(retry.empty_state(TODAY), "a", "hard", TODAY)
    state = retry.record_attempt(state, "a", False, TODAY)
    assert [r["id"] for r in retry.pending(state, TODAY)] == ["a"]
    state = retry.record_attempt(state, "a", False, TODAY)
    assert retry.pending(state, TODAY) == []  # default cap: 2 attempts
    assert retry.counts(state, TODAY) == {"failed": 1, "fixed": 0}


def test_state_from_an_earlier_day_is_ignored():
    old = retry.record_failure(retry.empty_state(TODAY), "a", "again", TODAY)
    tomorrow = TODAY + timedelta(days=1)
    assert retry.pending(old, tomorrow) == []
    fresh = retry.record_failure(old, "b", "hard", tomorrow)
    assert list(fresh["failed"]) == ["b"]


def test_record_attempt_for_unknown_card_raises():
    with pytest.raises(KeyError):
        retry.record_attempt(retry.empty_state(TODAY), "nope", True, TODAY)


# ---------------------------------------------------------------- CLI flow

@pytest.fixture(autouse=True)
def isolated_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def run(*args):
    out = io.StringIO()
    with redirect_stdout(out):
        cli.main(list(args))
    text = out.getvalue().strip()
    return json.loads(text) if text else None


@pytest.fixture
def deck():
    run(
        "init", "--native", "ru", "--target-language", "de",
        "--current-level", "B1", "--aim-level", "B2", "--target-date", "2027-01-01",
    )
    cards = {}
    for key, native, target in [
        ("again", "to prove", "beweisen"),
        ("hard", "to depend on", "abhängen (von)"),
        ("good", "the contract", "der Vertrag"),
    ]:
        cards[key] = run(
            "vocab-add", "--native-word", native, "--target-word", target, "--level", "B1"
        )["id"]
    return cards


def review_all(deck):
    for key, cid in deck.items():
        run("vocab-review", "--card-id", cid, "--rating", key)


def test_only_again_and_hard_enter_the_retry_list(deck):
    review_all(deck)
    listing = run("vocab-retry-list")
    assert listing["failed"] == 2
    assert [c["id"] for c in listing["pending"]] == [deck["again"], deck["hard"]]
    assert all("target_word" not in c for c in listing["pending"])  # answers stay hidden


def test_again_and_hard_both_count_as_a_lapse_on_a_learned_card(deck):
    review_all(deck)  # first look: never a lapse, for any rating
    cards = {c["id"]: c for c in db.load_db("vocab")["cards"]}
    assert all(c["lapses"] == 0 for c in cards.values())

    review_all(deck)  # second review of cards that are now in review state
    cards = {c["id"]: c for c in db.load_db("vocab")["cards"]}
    assert cards[deck["again"]]["lapses"] == 1
    assert cards[deck["hard"]]["lapses"] == 1
    assert cards[deck["good"]]["lapses"] == 0
    assert all("hards" not in c for c in cards.values())


def test_counting_hard_as_a_lapse_does_not_change_the_schedule(deck):
    """`lapses` is bookkeeping only: the FSRS state after `hard` is what fsrs.py computes."""
    from nachhilfe.fsrs import Card, Hard, review

    run("vocab-review", "--card-id", deck["hard"], "--rating", "hard")
    stored = next(c for c in db.load_db("vocab")["cards"] if c["id"] == deck["hard"])
    expected = review(Card(), Hard, date.today())
    assert stored["stability"] == round(expected.stability, 4)
    assert stored["difficulty"] == round(expected.difficulty, 4)
    assert stored["due"] == expected.due.isoformat()


def test_retry_record_never_touches_fsrs_state(deck):
    review_all(deck)
    before = {c["id"]: dict(c) for c in db.load_db("vocab")["cards"]}

    run("vocab-retry-record", "--card-id", deck["again"], "--result", "wrong")
    run("vocab-retry-record", "--card-id", deck["again"], "--result", "correct")
    run("vocab-retry-record", "--card-id", deck["hard"], "--result", "correct")

    after = {c["id"]: c for c in db.load_db("vocab")["cards"]}
    assert after == before


def test_retry_round_runs_until_fixed_or_out_of_attempts(deck):
    review_all(deck)
    r = run("vocab-retry-record", "--card-id", deck["again"], "--result", "wrong")
    assert r["fixed"] is False and r["remaining"] == 2
    run("vocab-retry-record", "--card-id", deck["hard"], "--result", "correct")

    listing = run("vocab-retry-list")
    assert [c["id"] for c in listing["pending"]] == [deck["again"]]
    assert listing["pending"][0]["attempts"] == 1
    assert listing["fixed"] == 1

    run("vocab-retry-record", "--card-id", deck["again"], "--result", "wrong")
    assert run("vocab-retry-list")["pending"] == []


def test_retry_record_rejects_a_card_that_was_not_failed(deck):
    review_all(deck)
    with pytest.raises(SystemExit):
        run("vocab-retry-record", "--card-id", deck["good"], "--result", "correct")


def test_logging_the_vocab_session_clears_the_retry_list(deck):
    review_all(deck)
    assert run("vocab-retry-list")["failed"] == 2
    run("session-log", "--type", "vocab", "--minutes", "10")
    assert run("vocab-retry-list") == {"failed": 0, "fixed": 0, "pending": []}


def test_other_session_types_leave_the_retry_list_alone(deck):
    review_all(deck)
    run("session-log", "--type", "writing", "--minutes", "10", "--score", "6")
    assert run("vocab-retry-list")["failed"] == 2


def test_suppressed_cards_are_not_due_and_can_be_restored(deck):
    run("vocab-suppress", "--card-id", deck["good"])
    assert deck["good"] not in [c["id"] for c in run("vocab-due", "--limit", "10")]
    run("vocab-suppress", "--card-id", deck["good"], "--undo")
    assert deck["good"] in [c["id"] for c in run("vocab-due", "--limit", "10")]
