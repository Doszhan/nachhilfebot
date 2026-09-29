"""Round-trip integration test for the db/cli layer, isolated from the
real data location by chdir'ing into tmp_path — the data root always
resolves to <cwd>/nachhilfe, so this alone is enough isolation.
"""
import io
import json
import subprocess
from contextlib import redirect_stdout

import pytest

from nachhilfe import cli, db


@pytest.fixture(autouse=True)
def isolated_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def run(*args) -> dict:
    out = io.StringIO()
    with redirect_stdout(out):
        cli.main(list(args))
    text = out.getvalue().strip()
    return json.loads(text) if text else None


def test_init_creates_profile_with_computed_targets():
    profile = run(
        "init",
        "--native", "en",
        "--target-language", "de",
        "--current-level", "B1",
        "--aim-level", "C1",
        "--target-date", "2027-01-01",
    )
    assert profile["target_language"] == "de"
    assert profile["hours_needed_total"] == 300  # B1->B2 (150) + B2->C1 (150)
    assert profile["daily_minutes_target"] > 0
    assert db.active_language() == "de"


def test_vocab_add_review_and_status_round_trip():
    run(
        "init", "--native", "en", "--target-language", "de",
        "--current-level", "B1", "--aim-level", "C1", "--target-date", "2027-01-01",
    )
    card = run("vocab-add", "--native-word", "the house", "--target-word", "das Haus", "--level", "A1")
    assert card["state"] == "new"

    due = run("vocab-due", "--limit", "5")
    assert [d["id"] for d in due] == [card["id"]]
    assert "target_word" not in due[0]  # answer must not leak before grading

    reveal = run("vocab-reveal", "--card-id", card["id"])
    assert reveal["target_word"] == "das Haus"

    reviewed = run("vocab-review", "--card-id", card["id"], "--rating", "good")
    assert reviewed["state"] == "review"
    assert reviewed["reps"] == 1

    assert run("vocab-due", "--limit", "5") == []  # not due again today

    run("session-log", "--type", "writing", "--minutes", "20", "--score", "7.5", "--topic", "formal email")

    status = run("status")
    assert status["vocab_mastery"]["in_learning"] == 1
    assert status["writing"]["average_last_5"] == 7.5
    assert status["streak"]["current"] == 1


def test_session_log_with_mistake_tags_updates_grammar_mistake_counts():
    run(
        "init", "--native", "en", "--target-language", "de",
        "--current-level", "B1", "--aim-level", "C1", "--target-date", "2027-01-01",
    )
    run(
        "session-log", "--type", "writing", "--minutes", "15", "--score", "6",
        "--mistake", "Genitiv", "--mistake", "Genitiv",
    )
    weak = run("grammar-weak")
    assert weak == [["Genitiv", 2]]


def test_session_log_stores_logged_at_and_status_lists_latest_first():
    run(
        "init", "--native", "en", "--target-language", "de",
        "--current-level", "B1", "--aim-level", "C1", "--target-date", "2027-01-01",
    )
    first = run("session-log", "--type", "vocab", "--minutes", "5")
    second = run("session-log", "--type", "writing", "--minutes", "10", "--score", "6")
    assert "T" in first["logged_at"]

    status = run("status")
    assert [s["id"] for s in status["last_sessions"]] == [second["id"], first["id"]]


def test_config_set_hours_overrides_default_table():
    run(
        "init", "--native", "en", "--target-language", "de",
        "--current-level", "B1", "--aim-level", "C1", "--target-date", "2027-01-01",
    )
    updated = run("config-set-hours", "--transition", "B1->B2", "--hours", "120")
    assert updated["transitions"]["B1->B2"] == 120

    status = run("status")
    assert status["progress"]["hours_needed"] == 120 + 150  # overridden B1->B2 + default B2->C1


def test_vocab_review_unknown_card_id_raises():
    run(
        "init", "--native", "en", "--target-language", "de",
        "--current-level", "B1", "--aim-level", "C1", "--target-date", "2027-01-01",
    )
    with pytest.raises(SystemExit):
        run("vocab-review", "--card-id", "does-not-exist", "--rating", "good")


def test_init_defaults_data_dir_to_current_directory(tmp_path):
    profile = run(
        "init", "--native", "en", "--target-language", "de",
        "--current-level", "B1", "--aim-level", "C1", "--target-date", "2027-01-01",
    )
    assert profile["data_dir"] == str(tmp_path / "nachhilfe")
    assert (tmp_path / "nachhilfe" / "de" / "vocab.json").exists()
    assert profile["data_dir_already_configured"] is False


def test_init_rerun_in_same_directory_is_flagged_already_configured(tmp_path):
    run(
        "init", "--native", "en", "--target-language", "de",
        "--current-level", "B1", "--aim-level", "C1", "--target-date", "2027-01-01",
    )
    profile2 = run(
        "init", "--native", "en", "--target-language", "de",
        "--current-level", "B1", "--aim-level", "C1", "--target-date", "2027-06-01",
    )
    assert profile2["data_dir_already_configured"] is True
    assert (tmp_path / "nachhilfe" / "de" / "vocab.json").exists()


def test_init_in_a_different_directory_creates_independent_data(tmp_path, monkeypatch):
    run(
        "init", "--native", "en", "--target-language", "de",
        "--current-level", "B1", "--aim-level", "C1", "--target-date", "2027-01-01",
    )
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    profile2 = run(
        "init", "--native", "en", "--target-language", "fr",
        "--current-level", "A1", "--aim-level", "B1", "--target-date", "2027-01-01",
    )
    # each cwd gets its own independent data root, by design
    assert profile2["data_dir"] == str(other_dir / "nachhilfe")
    assert profile2["data_dir_already_configured"] is False
    assert (other_dir / "nachhilfe" / "fr" / "vocab.json").exists()
    # the first directory's data is untouched and still resolvable from there
    assert (tmp_path / "nachhilfe" / "de" / "vocab.json").exists()


def test_commands_error_clearly_when_no_nachhilfe_dir_in_cwd(tmp_path, monkeypatch):
    other_dir = tmp_path / "nowhere"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)
    with pytest.raises(SystemExit):
        run("status")


def test_init_flags_when_data_dir_lands_in_a_git_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    profile = run(
        "init", "--native", "en", "--target-language", "de",
        "--current-level", "B1", "--aim-level", "C1", "--target-date", "2027-01-01",
    )
    assert profile["data_dir_in_git_repo"] is True


def test_init_no_git_warning_outside_a_repo(tmp_path):
    profile = run(
        "init", "--native", "en", "--target-language", "de",
        "--current-level", "B1", "--aim-level", "C1", "--target-date", "2027-01-01",
    )
    assert profile["data_dir_in_git_repo"] is False
