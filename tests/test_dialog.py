"""/nachhilfe-dialog: scenario choice, per-answer grading from sub-scores, logging."""
import io
import json
import random
from contextlib import redirect_stdout

import pytest

from nachhilfe import cli, db, dialog


# ---------------------------------------------------------------- pure logic

def test_there_is_no_fixed_scenario_list():
    assert not hasattr(dialog, "SCENARIOS")
    assert len(dialog.DOMAINS) >= 20  # broad areas of life only, a nudge


def test_a_session_is_reproducible_with_a_seed():
    first = dialog.build_session("B1", [], random.Random(7))
    assert first == dialog.build_session("B1", [], random.Random(7))
    assert first["scenario"] is None and first["results"] == []
    assert first["domain"] in dialog.DOMAINS


def test_the_domain_nudge_varies_and_surprises_are_sometimes_planned():
    domains, planned = set(), []
    for seed in range(200):
        session = dialog.build_session("B1", [], random.Random(seed))
        domains.add(session["domain"])
        planned.append(session["surprise_after_turn"])
    assert len(domains) >= 15
    assert None in planned and any(p is not None for p in planned)  # sometimes, not always
    assert all(p is None or 2 <= p <= dialog.DEFAULT_TURNS - 2 for p in planned)


def test_a_requested_situation_replaces_the_nudge_and_recent_titles_are_capped():
    session = dialog.build_session("B1", [f"t{i}" for i in range(50)], random.Random(1), request="at the pharmacy")
    assert session["request"] == "at the pharmacy" and session["domain"] is None
    assert session["recent_titles"] == [f"t{i}" for i in range(50 - dialog.RECENT_MEMORY, 50)]


def test_turn_score_adds_the_sub_scores_and_ranges_are_enforced():
    assert dialog.turn_score(4, 3, 3) == 10
    assert dialog.turn_score(0, 0, 0) == 0
    assert dialog.check_subscores(4, 3, 3) is None
    assert "fit" in dialog.check_subscores(5, 0, 0)
    assert "accuracy" in dialog.check_subscores(0, 4, 0)
    assert "natural" in dialog.check_subscores(0, 0, -1)


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


def fail(*args) -> str:
    with pytest.raises(SystemExit) as info:
        run(*args)
    return str(info.value)


@pytest.fixture
def learner():
    run("init", "--native", "ru", "--target-language", "de",
        "--current-level", "B1", "--aim-level", "B2", "--target-date", "2027-01-01")


def grade(fit, accuracy, natural, *extra):
    return run("dialog-record", "--fit", str(fit), "--accuracy", str(accuracy),
               "--natural", str(natural), *extra)


def begin(title="Cancelling a gym membership", *start_args):
    started = run("dialog-start", *start_args)
    run("dialog-setup", "--title", title)
    return started


def test_start_opens_a_dialog_and_a_second_start_resumes_it(learner):
    first = run("dialog-start", "--seed", "3")
    assert first["resumed"] is False and first["turns"] == dialog.DEFAULT_TURNS
    assert first["domain"] in dialog.DOMAINS and first["level"] == "B1" and first["scenario"] is None
    again = run("dialog-start")
    assert again["resumed"] is True and again["domain"] == first["domain"]


def test_the_situation_is_registered_by_the_model_before_grading(learner):
    run("dialog-start", "--seed", "3")
    assert "Register the situation first" in fail(
        "dialog-record", "--fit", "1", "--accuracy", "1", "--natural", "1")
    assert "must not be empty" in fail("dialog-setup", "--title", "  ")
    assert run("dialog-setup", "--title", "Lost umbrella at the cinema")["scenario"]["title"] == "Lost umbrella at the cinema"
    assert run("dialog-start")["scenario"]["title"] == "Lost umbrella at the cinema"  # resumed
    grade(3, 2, 2)
    assert "already begun" in fail("dialog-setup", "--title", "Something else")


def test_a_requested_situation_replaces_the_open_dialog(learner):
    run("dialog-start", "--seed", "3")
    asked = run("dialog-start", "--request", "at the pharmacy")
    assert asked["resumed"] is False and asked["request"] == "at the pharmacy" and asked["domain"] is None


def test_recording_needs_an_open_dialog_and_valid_sub_scores(learner):
    assert "No dialog is open" in fail("dialog-record", "--fit", "1", "--accuracy", "1", "--natural", "1")
    begin()
    assert "fit must be between 0 and 4" in fail(
        "dialog-record", "--fit", "5", "--accuracy", "1", "--natural", "1")
    assert "exact strings" in fail(
        "dialog-record", "--fit", "1", "--accuracy", "1", "--natural", "1", "--mistake", "Made-up topic")


def test_full_dialog_scores_logs_and_feeds_status(learner):
    start = begin("Cancelling a gym membership", "--seed", "3", "--turns", "4")
    assert start["turns"] == 4
    first = grade(4, 3, 3)
    assert first["score"] == 10 and first["remaining"] == 3
    grade(3, 1, 2, "--mistake", "Genitiv")
    grade(2, 2, 1)
    assert fail("dialog-finish", "--minutes", "8").startswith("Only 3 of 4")
    last = grade(1, 0, 1, "--mistake", "Genitiv", "--mistake", "Relativsätze")
    assert last["remaining"] == 0
    assert "All answers" in fail("dialog-record", "--fit", "1", "--accuracy", "1", "--natural", "1")

    result = run("dialog-finish", "--minutes", "8")
    assert result["score"] == 5.8  # mean of 10, 6, 5, 2 = 5.75
    assert [t["score"] for t in result["turn_scores"]] == [10, 6, 5, 2]
    assert result["weakest_turn"] == 4
    assert result["grammar_mistakes"] == [["Genitiv", 2], ["Relativsätze", 1]]
    assert result["session"]["type"] == "dialog" and result["session"]["minutes"] == 8
    assert result["session"]["topic"] == "Cancelling a gym membership"

    weak = dict(run("grammar-weak", "--limit", "10"))
    assert weak["Genitiv"] == 2
    assert run("status")["dialog"]["average_last_5"] == result["score"]
    assert db.load_db("dialog")["recent"] == ["Cancelling a gym membership"]
    assert fail("dialog-record", "--fit", "1", "--accuracy", "1", "--natural", "1").startswith("No dialog is open")


def test_played_situations_are_shown_next_time_and_cannot_be_repeated(learner):
    begin("Booking a doctor's appointment", "--turns", "4")
    for _ in range(4):
        grade(3, 2, 2)
    run("dialog-finish", "--minutes", "5")

    nxt = run("dialog-start", "--new", "--turns", "4")
    assert nxt["recent_titles"] == ["Booking a doctor's appointment"]
    assert "played recently" in fail("dialog-setup", "--title", "booking a doctor's appointment")
    run("dialog-setup", "--title", "A noisy neighbour")


def test_a_surprise_is_flagged_on_its_turn(learner):
    for seed in range(40):
        start = run("dialog-start", "--new", "--seed", str(seed), "--turns", "6")
        planned = start["surprise_after_turn"]
        if planned:
            run("dialog-setup", "--title", f"Situation {seed}")
            flags = [grade(3, 2, 2)["surprise_due"] for _ in range(6)]
            assert flags.index(True) == planned - 1 and flags.count(True) == 1
            return
    pytest.fail("no seed planned a surprise")


def test_partial_dialog_can_be_finished_when_allowed(learner):
    begin("Asking for directions", "--seed", "1")
    grade(4, 3, 3)
    assert fail("dialog-finish", "--minutes", "3").startswith("Only 1 of")
    result = run("dialog-finish", "--minutes", "3", "--allow-partial")
    assert result["score"] == 10.0 and result["answered"] == 1


def test_item_scores_are_averaged_by_the_plugin(learner):
    logged = run("session-log", "--type", "grammar", "--minutes", "10",
                 "--item-score", "8", "--item-score", "10", "--item-score", "5.5")
    assert logged["score"] == 7.8
    assert "not both" in fail("session-log", "--type", "grammar", "--minutes", "5",
                              "--score", "7", "--item-score", "8")
    assert "between 0 and 10" in fail("session-log", "--type", "grammar", "--minutes", "5",
                                      "--item-score", "11")
