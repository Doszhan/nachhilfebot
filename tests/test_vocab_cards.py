"""Vocab cards: editing the native word, example sentences, synonym decisions."""
import io
import json
from contextlib import redirect_stdout

import pytest

from nachhilfe import cli, vocab

EXAMPLES = [
    {"target": "Ich habe eine Beschwerde eingereicht.", "native": "I filed a complaint."},
    {"target": "Die Beschwerde wurde abgelehnt.", "native": "The complaint was rejected."},
    {"target": "Er schreibt eine Beschwerde an den Vermieter.", "native": "He writes a complaint to the landlord."},
]


# ---------------------------------------------------------------- pure logic

def _card(cid, native, **extra):
    return {"id": cid, "native_word": native, "target_word": "x", "created_at": "2026-11-01", **extra}


def test_recent_cards_put_the_latest_first_and_skip_hidden_cards():
    cards = [
        _card("old", "a", last_review="2026-11-01"),
        _card("new", "b"),  # added, never reviewed: ranks by its creation date
        _card("mid", "c", last_review="2026-11-05"),
        _card("hidden", "d", last_review="2026-11-20", suppressed=True),
        _card("late", "e", last_review="2026-11-05", last_reviewed_at="2026-11-05T18:30:00"),
    ]
    assert [c["id"] for c in vocab.recent_cards(cards)] == ["late", "mid", "new", "old"]
    assert [c["id"] for c in vocab.recent_cards(cards, limit=2)] == ["late", "mid"]


def test_duplicate_native_ignores_case_spacing_hidden_cards_and_the_card_itself():
    cards = [_card("a", "to claim"), _card("b", "the  Deadline"), _card("c", "gone", suppressed=True)]
    assert vocab.duplicate_native(cards, "THE deadline", "a")["id"] == "b"
    assert vocab.duplicate_native(cards, "to claim", "a") is None
    assert vocab.duplicate_native(cards, "gone", "a") is None


def test_examples_need_exactly_three_complete_distinct_pairs():
    clean, problem = vocab.check_examples(EXAMPLES)
    assert problem is None and clean == EXAMPLES
    assert vocab.check_examples(EXAMPLES[:2])[1]
    assert vocab.check_examples("text")[1]
    assert "non-empty" in vocab.check_examples(EXAMPLES[:2] + [{"target": "Hallo", "native": " "}])[1]
    assert "differ" in vocab.check_examples(EXAMPLES[:2] + [{"target": "Hallo", "native": "hallo"}])[1]
    assert "repeats" in vocab.check_examples(EXAMPLES[:2] + [dict(EXAMPLES[0])])[1]


def test_a_new_synonym_decision_replaces_an_old_one():
    card = _card("a", "x")
    assert vocab.record_synonym(card, "Aufwand", True) == {"accepted": ["Aufwand"], "rejected": []}
    assert vocab.record_synonym(card, " aufwand ", False) == {"accepted": [], "rejected": ["aufwand"]}
    assert vocab.synonym_lists(_card("b", "y")) == {"accepted": [], "rejected": []}


# ---------------------------------------------------------------- CLI flow

@pytest.fixture(autouse=True)
def isolated_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run("init", "--native", "ru", "--target-language", "de",
        "--current-level", "B1", "--aim-level", "B2", "--target-date", "2027-01-01")


def run(*args, stdin=None, monkeypatch=None):
    out = io.StringIO()
    if stdin is not None:
        import sys
        old, sys.stdin = sys.stdin, io.StringIO(stdin)
    try:
        with redirect_stdout(out):
            cli.main(list(args))
    finally:
        if stdin is not None:
            sys.stdin = old
    text = out.getvalue().strip()
    return json.loads(text) if text else None


def fail(*args, stdin=None) -> str:
    with pytest.raises(SystemExit) as info:
        run(*args, stdin=stdin)
    return str(info.value)


def add(native, target="x"):
    return run("vocab-add", "--native-word", native, "--target-word", target, "--level", "B2")["id"]


def test_recent_lists_the_cards_in_the_order_they_were_reviewed():
    first, second, third = add("one", "eins"), add("two", "zwei"), add("three", "drei")
    run("vocab-review", "--card-id", first, "--rating", "good")
    run("vocab-review", "--card-id", third, "--rating", "good")
    run("vocab-review", "--card-id", second, "--rating", "good")
    assert [c["id"] for c in run("vocab-recent")] == [second, third, first]
    assert len(run("vocab-recent", "--limit", "1")) == 1
    assert run("vocab-recent")[0]["target_word"] == "zwei"


def test_edit_native_changes_only_the_native_word_and_keeps_the_schedule():
    cid = add("to suggest", "vorschlagen")
    reviewed = run("vocab-review", "--card-id", cid, "--rating", "good")
    result = run("vocab-edit-native", "--card-id", cid, "--native-word", "  to propose ")
    assert result["previous_native_word"] == "to suggest" and result["native_word"] == "to propose"
    card = next(c for c in run("vocab-recent") if c["id"] == cid)
    assert card["native_word"] == "to propose" and card["target_word"] == "vorschlagen"
    assert run("vocab-reveal", "--card-id", cid)["native_word"] == "to propose"
    assert "to propose" in run("vocab-words")
    # the schedule (due date) is untouched
    due = {c["id"]: c for c in run("vocab-due", "--limit", "50")}
    assert cid not in due and reviewed["due"] > "2026"


def test_edit_native_refuses_empty_unchanged_and_duplicate_words():
    a, b = add("complaint", "Beschwerde"), add("deadline", "Frist")
    assert "must not be empty" in fail("vocab-edit-native", "--card-id", a, "--native-word", "   ")
    assert "nothing to change" in fail("vocab-edit-native", "--card-id", a, "--native-word", "complaint")
    assert "already uses" in fail("vocab-edit-native", "--card-id", a, "--native-word", "Deadline")
    assert "No such card" in fail("vocab-edit-native", "--card-id", "nope", "--native-word", "x")
    assert b  # untouched card still there


def test_examples_are_stored_once_and_shown_on_every_reveal():
    cid = add("complaint", "die Beschwerde")
    assert run("vocab-reveal", "--card-id", cid)["examples"] == []
    stored = run("vocab-examples", "--card-id", cid, stdin=json.dumps(EXAMPLES))
    assert stored["examples"] == EXAMPLES
    assert run("vocab-reveal", "--card-id", cid)["examples"] == EXAMPLES
    assert "already has examples" in fail("vocab-examples", "--card-id", cid, stdin=json.dumps(EXAMPLES))
    swapped = EXAMPLES[::-1]
    run("vocab-examples", "--card-id", cid, "--replace", stdin=json.dumps(swapped))
    assert run("vocab-reveal", "--card-id", cid)["examples"] == swapped


def test_bad_examples_are_rejected_and_nothing_is_stored():
    cid = add("complaint", "die Beschwerde")
    assert "exactly 3" in fail("vocab-examples", "--card-id", cid, stdin=json.dumps(EXAMPLES[:2]))
    assert "valid JSON" in fail("vocab-examples", "--card-id", cid, stdin="not json")
    assert run("vocab-reveal", "--card-id", cid)["examples"] == []


def test_examples_do_not_leak_through_the_question_side_commands():
    cid = add("complaint", "die Beschwerde")
    run("vocab-examples", "--card-id", cid, stdin=json.dumps(EXAMPLES))
    for out in (run("vocab-due"), run("vocab-recent")):
        assert "Beschwerde eingereicht" not in json.dumps(out, ensure_ascii=False)
    run("vocab-review", "--card-id", cid, "--rating", "again")
    pending = run("vocab-retry-list")["pending"]
    assert "examples" not in pending[0] and "target_word" not in pending[0]


def test_synonym_decisions_are_remembered_and_shown_on_reveal():
    cid = add("effort", "die Anstrengung")
    first = run("vocab-reveal", "--card-id", cid)
    assert first["accepted_synonyms"] == [] and first["rejected_synonyms"] == []
    run("vocab-synonym", "--card-id", cid, "--word", "der Aufwand", "--verdict", "accept")
    run("vocab-synonym", "--card-id", cid, "--word", "die Mühe", "--verdict", "reject")
    seen = run("vocab-reveal", "--card-id", cid)
    assert seen["accepted_synonyms"] == ["der Aufwand"] and seen["rejected_synonyms"] == ["die Mühe"]
    run("vocab-synonym", "--card-id", cid, "--word", "die Mühe", "--verdict", "accept")
    assert run("vocab-reveal", "--card-id", cid)["accepted_synonyms"] == ["der Aufwand", "die Mühe"]
    assert "must not be empty" in fail("vocab-synonym", "--card-id", cid, "--word", " ", "--verdict", "accept")
