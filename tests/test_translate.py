"""Translate exercise: deterministic planning, validation, matching, scoring."""
import io
import json
import random
from contextlib import redirect_stdout
from datetime import date

import pytest

from nachhilfe import cli, db, translate as tr

TODAY = date(2026, 11, 11)


def card(cid, native, target, **kw):
    base = {
        "id": cid, "native_word": native, "target_word": target, "level": "B1",
        "state": "review", "reps": 3, "lapses": 0, "stability": 30.0,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------- text matching

def test_normalize_drops_punctuation_and_case_but_keeps_umlauts():
    assert tr.normalize("Ich  bin, überfüllt!") == "ich bin überfüllt"


def test_match_token_statuses():
    answer = tr.tokens("Ich beschäftige mich mit der überfullt Gesellschaft")
    assert tr.match_token("mit", answer)["status"] == "exact"
    assert tr.match_token("überfüllt", answer) == {"status": "umlaut", "found": "überfullt"}
    assert tr.match_token("Gesellschaften", answer)["status"] == "similar"
    assert tr.match_token("Voraussetzung", answer)["status"] == "missing"


def test_short_words_such_as_prepositions_must_match_exactly():
    # 'für' vs 'fur' folds to the same letters, but 'für' vs 'vor' must never count
    assert tr.match_token("für", tr.tokens("Ich begeistere mich vor Musik"))["status"] == "missing"
    assert tr.match_token("für", tr.tokens("Ich begeistere mich fur Musik"))["status"] == "umlaut"


def test_check_keys_flags_the_wrong_preposition_and_missing_reflexive():
    keys = [{"card_id": "c1", "tokens": ["begeistere", "mich", "für"]}]
    ok = tr.check_keys(keys, "Ich begeistere mich für Musik")[0]
    assert ok["verdict"] == "ok"

    wrong_prep = tr.check_keys(keys, "Ich begeistere mich über Musik")[0]
    assert wrong_prep["verdict"] == "missing"
    assert [t["want"] for t in wrong_prep["tokens"] if t["status"] == "missing"] == ["für"]

    no_sich = tr.check_keys(keys, "Ich begeistere für Musik")[0]
    assert [t["want"] for t in no_sich["tokens"] if t["status"] == "missing"] == ["mich"]


def test_check_keys_spelling_verdict_when_all_words_found_but_not_exact():
    keys = [{"card_id": "c1", "tokens": ["überfüllt"]}]
    assert tr.check_keys(keys, "Der Zug ist überfullt")[0]["verdict"] == "spelling"


# ---------------------------------------------------------------- grammar markers

@pytest.mark.parametrize(
    "topic,text,expected",
    [
        ("Konzessivsätze (obwohl)", "Obwohl es regnet, gehen wir.", True),
        ("Konzessivsätze (obwohl)", "Es regnet, aber wir gehen.", False),
        ("Finalsätze (damit/um...zu)", "Ich lerne, um die Prüfung zu bestehen.", True),
        ("Finalsätze (damit/um...zu)", "Ich lerne viel.", False),
        ("Relativsätze", "Das ist der Mann, der hier wohnt.", True),
        ("Relativsätze", "Das ist der Mann mit dem Hut.", False),  # not after a comma
        ("Indirekte Fragesätze", "Ich weiß nicht, ob er kommt.", True),
        ("Genitiv", "Wegen des Wetters bleiben wir.", True),
        ("Präteritum (alle Verben)", "Er ging nach Hause.", None),  # no detectable marker
        ("Unknown topic", "irgendwas", None),
    ],
)
def test_marker_found(topic, text, expected):
    assert tr.marker_found("de", topic, text) is expected


def test_other_target_languages_get_no_marker_checks_or_hints():
    assert tr.marker_found("fr", "Relativsätze", "qui") is None
    assert tr.topic_hint("fr", "Relativsätze") is None


# ---------------------------------------------------------------- choosing targets

def test_weakness_rewards_lapses_and_recent_translate_misses():
    plain = card("a", "x", "y")
    lapsed = card("b", "x", "y", lapses=2)
    assert tr.weakness(lapsed, {}, TODAY) == 6
    assert tr.weakness(plain, {"missed": 2, "hit": 0}, TODAY) == 6
    # a later hit cancels one miss
    assert tr.weakness(plain, {"missed": 2, "hit": 1}, TODAY) == 3


def test_weakness_penalises_words_practiced_in_the_last_three_days():
    c = card("a", "x", "y", lapses=1)
    fresh = tr.weakness(c, {"last_seen": "2026-11-10"}, TODAY)
    old = tr.weakness(c, {"last_seen": "2026-11-01"}, TODAY)
    assert old - fresh == 3


def test_rank_cards_skips_new_and_suppressed_cards_and_puts_the_weakest_first():
    cards = [
        card("ok", "a", "b"),
        card("weak", "a", "b", lapses=4),
        card("gone", "a", "b", lapses=9, suppressed=True),
        card("new", "a", "b", reps=0, state="new", lapses=9),
    ]
    assert [c["id"] for c in tr.rank_cards(cards, {}, TODAY)] == ["weak", "ok"]


def test_allocate_topics_follows_mistake_counts_with_a_cap():
    rng = random.Random(1)
    counts = {"Adjektivdeklination (vollständig)": 16, "Relativsätze": 3, "Genitiv": 1}
    topics = tr.allocate_topics(counts, ["Passiv (Präsens/Präteritum)"], 8, rng)
    assert len(topics) == 8
    assert topics.count("Adjektivdeklination (vollständig)") == 4  # capped at half
    assert topics.count("Relativsätze") >= 1


def test_allocate_topics_fills_with_other_level_topics_when_history_is_narrow():
    rng = random.Random(1)
    topics = tr.allocate_topics({"Genitiv": 5}, ["Relativsätze", "Passiv (Präsens/Präteritum)"], 6, rng)
    assert topics.count("Genitiv") == 3
    assert set(topics) <= {"Genitiv", "Relativsätze", "Passiv (Präsens/Präteritum)"}


def test_allocate_topics_without_history_cycles_the_level_topics():
    topics = tr.allocate_topics({}, ["A", "B"], 5, random.Random(0))
    assert sorted(topics) == ["A", "A", "A", "B", "B"]


def deck_of(n):
    cards = []
    for i in range(n):
        kind = ("to do", "verb %d" % i) if i % 2 == 0 else ("the thing", "das Ding %d" % i)
        cards.append(card(f"c{i}", kind[0], kind[1] if i % 2 else f"machen{i}", lapses=n - i))
    return cards


def test_build_slots_pairs_a_verb_with_a_noun_and_is_seeded():
    cards = [
        card("v1", "to prove", "beweisen", lapses=5),
        card("v2", "to claim", "behaupten", lapses=4),
        card("n1", "the reason", "der Grund", lapses=3),
        card("n2", "the risk", "das Risiko", lapses=2),
    ]
    kwargs = dict(
        cards=cards, stats={}, mistake_counts={"Genitiv": 3}, level_topics=["Relativsätze"],
        lang="de", today=TODAY, count=2, per_sentence=2, seed=7,
    )
    slots = tr.build_slots(**kwargs)
    assert len(slots) == 2
    for slot in slots:
        assert sorted(c["kind"] for c in slot["cards"]) == ["noun", "verb"]
    assert slots == tr.build_slots(**kwargs)  # same seed, same plan
    assert [s["n"] for s in slots] == [1, 2]
    assert slots[0]["grammar_hint"] or slots[1]["grammar_hint"]


def test_build_slots_shrinks_when_there_are_too_few_cards():
    cards = [card(f"c{i}", "to x", f"machen{i}", lapses=i) for i in range(3)]
    slots = tr.build_slots(cards, {}, {}, ["Genitiv"], "de", TODAY, count=8, per_sentence=2, seed=1)
    assert len(slots) == 3
    assert all(len(s["cards"]) == 1 for s in slots)


def test_build_slots_without_reviewed_cards_raises():
    with pytest.raises(ValueError):
        tr.build_slots([card("n", "x", "y", reps=0, state="new")], {}, {}, [], "de", TODAY)


# ---------------------------------------------------------------- validating the model's sentences

def slot(n=1, cards=("c1",), topic="Konzessivsätze (obwohl)"):
    return {
        "n": n, "grammar_topic": topic,
        "cards": [{"id": c, "native_word": "x", "target_word": "y", "kind": "verb"} for c in cards],
    }


def good_item(n=1):
    return {
        "n": n,
        "source": "Хотя идёт дождь, я интересуюсь музыкой.",
        "reference": "Obwohl es regnet, interessiere ich mich für Musik.",
        "keys": [{"card_id": "c1", "tokens": ["interessiere", "mich", "für"]}],
    }


def test_valid_submission_has_no_errors():
    assert tr.validate_submission([slot()], [good_item()], "de") == []


def test_submission_must_cover_exactly_the_planned_sentences():
    errors = tr.validate_submission([slot(1), slot(2)], [good_item(1), good_item(3)], "de")
    assert any("sentence 2: missing" in e for e in errors)
    assert any("sentence 3: not part of" in e for e in errors)


def test_key_tokens_must_appear_in_the_reference():
    item = good_item()
    item["keys"][0]["tokens"] = ["interessiere", "mich", "über"]
    errors = tr.validate_submission([slot()], [item], "de")
    assert any("'über'" in e and "does not appear" in e for e in errors)


def test_every_target_card_needs_a_key_and_no_foreign_cards_are_allowed():
    item = good_item()
    item["keys"].append({"card_id": "zzz", "tokens": ["musik"]})
    errors = tr.validate_submission([slot(cards=("c1", "c2"))], [item], "de")
    assert any("no key for target card c2" in e for e in errors)
    assert any("card zzz which is not a target" in e for e in errors)


def test_reference_must_show_the_requested_construction():
    item = good_item()
    item["reference"] = "Es regnet, aber ich interessiere mich für Musik."
    errors = tr.validate_submission([slot()], [item], "de")
    assert any("no marker of the requested grammar topic" in e for e in errors)


def test_target_word_must_not_leak_into_the_source_sentence():
    item = good_item()
    item["source"] = "Obwohl es regnet, interessiere ich mich für Musik."
    item["reference"] = item["source"] + " Danke."
    errors = tr.validate_submission([slot()], [item], "de")
    assert any("leak" in e for e in errors)


def test_identical_source_and_reference_is_rejected():
    item = good_item()
    item["source"] = item["reference"]
    assert any("identical" in e for e in tr.validate_submission([slot()], [item], "de"))


def test_non_list_submission_is_rejected():
    assert tr.validate_submission([slot()], {"n": 1}, "de") == ["submission must be a JSON list of objects"]


# ---------------------------------------------------------------- checking answers, scoring

SENTENCE = {
    "source": "...",
    "reference": "Obwohl es regnet, interessiere ich mich für Musik.",
    "keys": [{"card_id": "c1", "tokens": ["interessiere", "mich", "für"]}],
}


def test_exact_answer_ignores_case_and_punctuation():
    res = tr.check_answer("obwohl es regnet interessiere ich mich für musik", SENTENCE, "Konzessivsätze (obwohl)", "de")
    assert res["exact_match"] is True
    assert res["grammar_marker_found"] is True


def test_answer_without_the_construction_is_flagged_as_possibly_avoided():
    res = tr.check_answer("Es regnet, ich interessiere mich für Musik", SENTENCE, "Konzessivsätze (obwohl)", "de")
    assert res["exact_match"] is False
    assert res["grammar_marker_found"] is False
    assert res["keys"][0]["verdict"] == "ok"


def test_score_out_of_10_counts_partial_as_half():
    assert tr.score_out_of_10(["correct", "correct", "partial", "wrong"]) == 6.2
    assert tr.score_out_of_10(["correct"] * 3) == 10.0
    assert tr.score_out_of_10([]) == 0.0


def test_card_outcome_and_stats():
    ok = {"card_id": "c1", "verdict": "ok"}
    spelling = {"card_id": "c1", "verdict": "spelling"}
    missing = {"card_id": "c1", "verdict": "missing"}
    assert tr.card_outcome(ok, set()) == "hit"
    assert tr.card_outcome(spelling, set()) == "spelling"
    assert tr.card_outcome(missing, set()) == "miss"
    assert tr.card_outcome(missing, {"c1"}) == "hit"  # model accepted an equal expression

    stats = {}
    tr.update_stats(stats, "c1", "miss", TODAY)
    tr.update_stats(stats, "c1", "spelling", TODAY)
    assert stats["c1"] == {
        "seen": 2, "hit": 1, "missed": 1, "spelling": 1, "last_seen": TODAY.isoformat(),
    }


# ---------------------------------------------------------------- full CLI flow

@pytest.fixture
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


PREFIX = {  # a phrase containing the marker of each B1 topic
    "Präteritum (alle Verben)": "Gestern ging ich nach Hause",
    "Konjunktiv II (Höflichkeit, irreale Bedingungssätze)": "Ich würde gern",
    "Passiv (Präsens/Präteritum)": "Es wird gesagt",
    "Relativsätze": "Das ist der Mann, der",
    "Genitiv": "Wegen des Wetters",
    "Temporalsätze (als/wenn/während/nachdem)": "Als ich jung war",
    "Kausalsätze (weil/da/denn)": "Weil es regnet",
    "Konzessivsätze (obwohl)": "Obwohl es regnet",
    "Finalsätze (damit/um...zu)": "Damit alles klappt",
    "Indirekte Fragesätze": "Ich weiß nicht, ob",
    "Adjektivdeklination (vollständig)": "Ein neues Auto",
}

CARDS = [  # native, target, key tokens, rating
    ("to prove", "beweisen", ["beweist"], "again"),
    ("to depend on", "abhängen (von)", ["hängt", "ab", "von"], "hard"),
    ("the reason", "der Grund, die Gründe", ["grund"], "again"),
    ("to claim", "behaupten", ["behauptet"], "hard"),
]


@pytest.fixture
def session(isolated_root):
    run(
        "init", "--native", "ru", "--target-language", "de",
        "--current-level", "B1", "--aim-level", "B2", "--target-date", "2027-01-01",
    )
    keys = {}
    for native, target, tokens_, rating in CARDS:
        cid = run("vocab-add", "--native-word", native, "--target-word", target, "--level", "B1")["id"]
        run("vocab-review", "--card-id", cid, "--rating", rating)
        keys[cid] = tokens_
    run("session-log", "--type", "grammar", "--minutes", "5", "--score", "5",
        "--mistake", "Adjektivdeklination (vollständig)", "--mistake", "Adjektivdeklination (vollständig)",
        "--mistake", "Relativsätze")
    plan = run("translate-start", "--count", "2", "--per-sentence", "2", "--seed", "3")
    return plan, keys


def submission(plan, keys):
    items = []
    for s in plan["slots"]:
        words = [t for c in s["cards"] for t in keys[c["id"]]]
        items.append(
            {
                "n": s["n"],
                "source": f"Предложение номер {s['n']}",
                "reference": f"{PREFIX[s['grammar_topic']]} {' '.join(words)}.",
                "keys": [{"card_id": c["id"], "tokens": keys[c["id"]]} for c in s["cards"]],
            }
        )
    return items


def test_start_plans_sentences_from_weak_cards_and_topics(session):
    plan, keys = session
    assert plan["source_language"] == "ru"  # first native language by default
    assert plan["level"] == "B1"
    assert len(plan["slots"]) == 2
    assert {c["id"] for s in plan["slots"] for c in s["cards"]} == set(keys)
    assert "Adjektivdeklination (vollständig)" in {s["grammar_topic"] for s in plan["slots"]}


def test_preview_does_not_open_a_session(isolated_root):
    run("init", "--native", "ru", "--target-language", "de", "--current-level", "B1",
        "--aim-level", "B2", "--target-date", "2027-01-01")
    cid = run("vocab-add", "--native-word", "to prove", "--target-word", "beweisen", "--level", "B1")["id"]
    run("vocab-review", "--card-id", cid, "--rating", "again")
    run("translate-start", "--preview", "--count", "1", "--per-sentence", "1")
    assert fail("translate-next").startswith("No translate session is open")


def test_start_without_reviewed_cards_explains_what_to_do(isolated_root):
    run("init", "--native", "ru", "--target-language", "de", "--current-level", "B1",
        "--aim-level", "B2", "--target-date", "2027-01-01")
    assert "vocab session first" in fail("translate-start")


def test_source_language_can_be_configured(isolated_root):
    run("init", "--native", "kk,ru", "--target-language", "de", "--current-level", "B1",
        "--aim-level", "B2", "--target-date", "2027-01-01")
    assert run("translate-config")["default_source_language"] == "kk"
    assert run("translate-config", "--source-language", "Russian")["source_language"] == "Russian"


def test_second_start_on_the_same_day_resumes_the_open_session(session):
    plan, keys = session
    run("translate-submit", "--json", json.dumps(submission(plan, keys)))
    again = run("translate-start")
    assert again["resumed"] is True
    assert again["sentences_submitted"] is True
    assert again["slots"] == plan["slots"]


def test_bad_sentences_are_rejected_with_reasons_and_nothing_is_stored(session):
    plan, keys = session
    items = submission(plan, keys)
    items[0]["keys"][0]["tokens"] = ["gibtesnicht"]
    message = fail("translate-submit", "--json", json.dumps(items))
    assert "Sentences rejected" in message and "gibtesnicht" in message
    assert fail("translate-next").startswith("No sentences submitted yet")


def test_next_shows_only_the_source_sentence(session):
    plan, keys = session
    run("translate-submit", "--json", json.dumps(submission(plan, keys)))
    nxt = run("translate-next")
    assert nxt["n"] == 1 and nxt["total"] == 2 and nxt["source"].startswith("Предложение")
    assert "reference" not in nxt


def test_full_session_scores_updates_stats_and_logs(session):
    plan, keys = session
    items = submission(plan, keys)
    run("translate-submit", "--json", json.dumps(items))

    # sentence 1: exact -> verdict is recorded automatically
    checked = run("translate-check", "--n", "1", "--answer", items[0]["reference"].lower())
    assert checked["exact_match"] and checked["verdict_recorded"]
    assert "already has a verdict" in fail("translate-record", "--n", "1", "--verdict", "wrong")

    # sentence 2: drop a required word and the construction
    wrong = run("translate-check", "--n", "2", "--answer", "Ich weiß es nicht")
    assert not wrong["verdict_recorded"]
    assert wrong["reference"] == items[1]["reference"]
    assert any(k["verdict"] == "missing" for k in wrong["keys"])

    # the code refuses a lenient 'correct' while target words are missing
    assert "not allowed" in fail("translate-record", "--n", "2", "--verdict", "correct")
    assert "exact strings" in fail(
        "translate-record", "--n", "2", "--verdict", "wrong", "--mistake", "Made-up topic"
    )
    run("translate-record", "--n", "2", "--verdict", "wrong", "--mistake", "Relativsätze")

    assert run("translate-next")["done"] is True
    result = run("translate-finish", "--minutes", "9")

    assert result["score"] == 5.0
    assert (result["correct"], result["partial"], result["wrong"]) == (1, 0, 1)
    assert result["grammar_mistakes"] == [["Relativsätze", 1]]
    assert len(result["vocab_missed"]) == len(items[1]["keys"])
    assert result["session"]["type"] == "translate"
    assert result["session"]["minutes"] == 9

    # grammar counts feed the weak-topic ranking
    weak = dict(run("grammar-weak", "--limit", "10"))
    assert weak["Relativsätze"] == 2  # 1 from the grammar session, 1 from translate

    # per-word stats were written, the status report shows the new discipline, session is closed
    stats = db.load_db("translate")["cards"]
    missed_ids = {m["id"] for m in result["vocab_missed"]}
    assert all(stats[i]["missed"] == 1 for i in missed_ids)
    assert run("status")["translate"]["average_last_5"] == 5.0
    assert fail("translate-next").startswith("No translate session is open")


def test_accepting_an_equivalent_expression_allows_correct(session):
    plan, keys = session
    items = submission(plan, keys)
    run("translate-submit", "--json", json.dumps(items))
    # the learner keeps the construction but swaps in a different word for card 1
    slot_cards = [c["id"] for c in plan["slots"][0]["cards"]]
    words = [t for cid in slot_cards[1:] for t in keys[cid]]
    answer = f"{PREFIX[plan['slots'][0]['grammar_topic']]} synonym {' '.join(words)}"
    checked = run("translate-check", "--n", "1", "--answer", answer)
    assert not checked["verdict_recorded"]
    assert "not allowed" in fail("translate-record", "--n", "1", "--verdict", "correct")
    run("translate-record", "--n", "1", "--verdict", "correct", "--accept", slot_cards[0])


def test_correct_verdict_cannot_carry_mistake_tags(session):
    plan, keys = session
    items = submission(plan, keys)
    run("translate-submit", "--json", json.dumps(items))
    # all target words present, but not word-for-word the reference -> the model must judge
    answer = items[0]["reference"].replace(".", " sehr.")
    checked = run("translate-check", "--n", "1", "--answer", answer)
    assert not checked["exact_match"] and not checked["verdict_recorded"]
    assert all(k["verdict"] == "ok" for k in checked["keys"])
    assert "cannot carry mistake tags" in fail(
        "translate-record", "--n", "1", "--verdict", "correct", "--mistake", "Relativsätze"
    )
    run("translate-record", "--n", "1", "--verdict", "correct")


def test_finish_requires_all_sentences_unless_partial_is_allowed(session):
    plan, keys = session
    items = submission(plan, keys)
    run("translate-submit", "--json", json.dumps(items))
    run("translate-check", "--n", "1", "--answer", items[0]["reference"])
    assert "Sentences without a verdict" in fail("translate-finish", "--minutes", "5")
    result = run("translate-finish", "--minutes", "5", "--allow-partial")
    assert result["answered"] == 1 and result["total"] == 2 and result["score"] == 10.0


def test_answer_can_be_read_from_stdin(session, monkeypatch):
    plan, keys = session
    items = submission(plan, keys)
    run("translate-submit", "--json", json.dumps(items))
    monkeypatch.setattr("sys.stdin", io.StringIO(items[0]["reference"]))
    assert run("translate-check", "--n", "1")["exact_match"] is True


def test_a_session_always_has_the_same_fixed_number_of_sentences(isolated_root):
    assert tr.DEFAULT_COUNT == 5
    run("init", "--native", "ru", "--target-language", "de", "--current-level", "B1",
        "--aim-level", "B2", "--target-date", "2027-01-01")
    for i in range(12):
        cid = run("vocab-add", "--native-word", f"to do {i}", "--target-word", f"machen{i}",
                  "--level", "B1")["id"]
        run("vocab-review", "--card-id", cid, "--rating", "good")
    plan = run("translate-start", "--preview")
    assert len(plan["slots"]) == 5
    assert all(len(s["cards"]) == 2 for s in plan["slots"])
