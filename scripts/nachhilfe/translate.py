"""Deterministic core of /nachhilfe-translate.

The learner translates sentences from their native language into the target
language. Everything that can be computed is computed here, so the model is
left with the parts only it can do (writing natural sentences, judging answers
that differ from the reference, explaining mistakes):

* which vocab cards and grammar topics to target, ranked by the learner's
  own failure history;
* validating the model's generated sentences (do they really contain the
  target words and the requested construction?);
* matching the learner's answer against the required words, token by token;
* scoring and the per-card / per-topic bookkeeping.

German-specific grammar knowledge (construction hints and detectable
markers) lives in `GRAMMAR_PROFILES`; other target languages simply get no
hints and no marker checks.
"""
from __future__ import annotations

import difflib
import math
import random
import re
import unicodedata
from datetime import date

DEFAULT_COUNT = 5  # sentences per session; fixed so every session is the same size
DEFAULT_PER_SENTENCE = 2
SIMILARITY_THRESHOLD = 0.8
MIN_FUZZY_LEN = 5

VERDICTS = ("correct", "partial", "wrong")


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------

def normalize(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace. Umlauts are kept."""
    text = unicodedata.normalize("NFC", text).lower()
    text = re.sub(r"[^\w\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> list[str]:
    return normalize(text).split()


def fold(token: str) -> str:
    """Strip diacritics and ß, so 'fur' == 'für' and 'strasse' == 'straße'."""
    token = token.replace("ß", "ss")
    decomposed = unicodedata.normalize("NFD", token)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def match_token(want: str, answer_tokens: list[str]) -> dict:
    """How does one required word appear in the learner's answer?

    status:
      exact    - the word is there, spelled as required
      umlaut   - same letters except umlaut/ß (e.g. 'fur' for 'für')
      similar  - a close but different token (typo, or another inflection);
                 `found` holds it so the model can tell which
      missing  - nothing close
    """
    w = normalize(want)
    if w in answer_tokens:
        return {"status": "exact", "found": w}
    wf = fold(w)
    for t in answer_tokens:
        if fold(t) == wf:
            return {"status": "umlaut", "found": t}
    if len(w) >= MIN_FUZZY_LEN:
        best_token, best_ratio = None, 0.0
        for t in answer_tokens:
            if len(t) < MIN_FUZZY_LEN - 1:
                continue
            ratio = difflib.SequenceMatcher(None, w, t).ratio()
            if ratio > best_ratio:
                best_token, best_ratio = t, ratio
        if best_token is not None and best_ratio >= SIMILARITY_THRESHOLD:
            return {"status": "similar", "found": best_token}
    return {"status": "missing", "found": None}


def key_tokens(key: dict) -> list[str]:
    """The required words of one key, flattened and normalized."""
    out: list[str] = []
    for item in key.get("tokens", []):
        out.extend(tokens(item))
    return out


def check_keys(keys: list[dict], answer: str) -> list[dict]:
    answer_tokens = tokens(answer)
    results = []
    for key in keys:
        per_token = [{"want": t, **match_token(t, answer_tokens)} for t in key_tokens(key)]
        statuses = {r["status"] for r in per_token}
        if statuses <= {"exact"}:
            verdict = "ok"
        elif "missing" in statuses:
            verdict = "missing"
        else:
            verdict = "spelling"
        results.append({"card_id": key["card_id"], "verdict": verdict, "tokens": per_token})
    return results


# --------------------------------------------------------------------------
# German grammar profile: how to build and detect each topic
# --------------------------------------------------------------------------

def _p(hint: str, *markers: str) -> dict:
    return {"hint": hint, "markers": list(markers)}


_PREP = r"(?:in|an|auf|mit|von|für|über|zu|bei|aus|nach|um|durch|unter|vor|gegen|ohne)"

GRAMMAR_PROFILES: dict[str, dict[str, dict]] = {
    "de": {
        "Präteritum (alle Verben)": _p(
            "Narrate in the past using Präteritum of a verb other than sein/haben "
            "(ideally a strong/irregular one)."
        ),
        "Konjunktiv II (Höflichkeit, irreale Bedingungssätze)": _p(
            "Use Konjunktiv II: a polite request or an unreal condition (wenn ich ..., würde/hätte/wäre ...).",
            r"\b(würde|würden|würdest|würdet|hätte|hätten|hättest|hättet|wäre|wären|wärst|wärt|"
            r"könnte|könnten|könntest|müsste|müssten|sollte|sollten|dürfte|möchte|möchten|"
            r"wollte|wollten|bräuchte|gäbe)\b",
        ),
        "Passiv (Präsens/Präteritum)": _p(
            "Use the Vorgangspassiv (wird/werden/wurde/wurden + Partizip II).",
            r"\b(wird|werden|wurde|wurden|wirst|werdet)\b",
        ),
        "Relativsätze": _p(
            "Include a relative clause (der/die/das/dem/den/dessen..., verb at the end of the clause).",
            r",\s*(?:" + _PREP + r"\s+)?(?:der|die|das|den|dem|denen|dessen|deren|welche[rsmn]?)\b",
        ),
        "Genitiv": _p(
            "Use a genitive: des/eines + noun, or a genitive preposition (wegen, trotz, während, statt).",
            r"\b(des|eines|dieses|jenes|wegen|trotz|statt|anstatt|außerhalb|innerhalb|aufgrund)\b",
        ),
        "Temporalsätze (als/wenn/während/nachdem)": _p(
            "Include a temporal subordinate clause (als / wenn / während / nachdem), verb at the end.",
            r"\b(als|wenn|während|nachdem|bevor|sobald|seitdem|solange)\b",
        ),
        "Kausalsätze (weil/da/denn)": _p(
            "Give a reason with weil or da (verb at the end) or denn (normal word order).",
            r"\b(weil|da|denn)\b",
        ),
        "Konzessivsätze (obwohl)": _p(
            "Include an obwohl-clause (verb at the end).",
            r"\b(obwohl|obgleich|obschon)\b",
        ),
        "Finalsätze (damit/um...zu)": _p(
            "Express a purpose with damit (new subject, verb at the end) or um ... zu + infinitive.",
            r"\bdamit\b",
            r"\bum\b.*\bzu\b",
        ),
        "Indirekte Fragesätze": _p(
            "Embed an indirect question after a main clause (ob, or a W-word; verb at the end).",
            r",\s*(?:ob|wann|wo|wie|warum|weshalb|wieso|wer|was|wen|wem|wessen|wohin|woher|welche[rsmn]?)\b",
            r"\bob\b",
        ),
        "Adjektivdeklination (vollständig)": _p(
            "Include at least two attributive adjectives in different declension situations "
            "(e.g. without article: 'frische Milch'; after der/die/das; after ein-/kein-)."
        ),
        "Adjektivdeklination (Grundlagen)": _p(
            "Include at least one attributive adjective with an article (ein neues Auto, der alte Mann)."
        ),
        "Reflexive Verben": _p(
            "Use a reflexive verb (sich + verb).",
            r"\b(mich|dich|sich|uns|euch)\b",
        ),
        "Trennbare Verben": _p("Use a separable verb with its prefix at the end of the main clause."),
        "Passiv mit Modalverben": _p(
            "Use the passive with a modal verb (muss/kann/soll ... + Partizip II + werden).",
            r"\b(muss|müssen|kann|können|soll|sollen|darf|dürfen|will|wollen|musste|konnte|sollte|durfte)\b.*\bwerden\b",
        ),
        "Doppelkonjunktionen (je...desto, sowohl...als auch)": _p(
            "Use a double conjunction (je ... desto, sowohl ... als auch, weder ... noch, nicht nur ... sondern auch).",
            r"\bje\b.*\bdesto\b",
            r"\bje\b.*\bumso\b",
            r"\bsowohl\b.*\bals auch\b",
            r"\bweder\b.*\bnoch\b",
            r"\bentweder\b.*\boder\b",
            r"\bnicht nur\b.*\bsondern auch\b",
        ),
        "Infinitivkonstruktionen (um...zu, ohne...zu, statt...zu)": _p(
            "Use um ... zu, ohne ... zu or statt ... zu with an infinitive.",
            r"\b(um|ohne|statt|anstatt)\b.*\bzu\b",
        ),
        "Konnektoren zur Textkohärenz (dennoch, folglich, allerdings)": _p(
            "Use a connector adverb (dennoch, folglich, allerdings, außerdem, deshalb).",
            r"\b(dennoch|folglich|allerdings|außerdem|deshalb|deswegen|trotzdem|jedoch|somit|demnach|hingegen)\b",
        ),
    }
}


def topic_hint(lang: str, topic: str | None) -> str | None:
    profile = GRAMMAR_PROFILES.get(lang, {}).get(topic or "")
    return profile["hint"] if profile else None


def marker_found(lang: str, topic: str | None, text: str) -> bool | None:
    """Does `text` contain a typical marker of `topic`?

    True/False when the topic has detectable markers, None when it doesn't
    (no check possible). This is a heuristic: a missing marker means "the
    learner may have avoided the construction", not "the grammar is wrong".
    """
    profile = GRAMMAR_PROFILES.get(lang, {}).get(topic or "")
    if not profile or not profile["markers"]:
        return None
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in profile["markers"])


# --------------------------------------------------------------------------
# Choosing what to practice
# --------------------------------------------------------------------------

def card_kind(card: dict) -> str:
    target = card["target_word"].strip().lower()
    if re.match(r"(der|die|das)\s", target):
        return "noun"
    if card["native_word"].strip().lower().startswith("to "):
        return "verb"
    return "other"


def weakness(card: dict, stat: dict, today: date) -> float:
    """Higher = the learner needs this word more.

    3 per lapse (rated again or hard), 3 per net miss in earlier
    translate sessions, +2 / +1 for low FSRS stability, and a small penalty
    when it was already practiced here in the last 3 days.
    """
    score = 3 * card.get("lapses", 0)
    score += 3 * max(0, stat.get("missed", 0) - stat.get("hit", 0))
    stability = card.get("stability") or 0
    if stability < 7:
        score += 2
    elif stability < 21:
        score += 1
    last_seen = stat.get("last_seen")
    if last_seen and (today - date.fromisoformat(last_seen)).days <= 3:
        score -= 3
    return score


def rank_cards(cards: list[dict], stats: dict, today: date) -> list[dict]:
    """Reviewed, non-suppressed cards, weakest first."""
    usable = [
        c for c in cards
        if c.get("reps", 0) >= 1 and not c.get("suppressed") and c.get("target_word")
    ]
    usable.sort(
        key=lambda c: (
            -weakness(c, stats.get(c["id"], {}), today),
            c.get("stability") or 0,
            c["id"],
        )
    )
    return usable


def allocate_topics(
    mistake_counts: dict, level_topics: list[str], count: int, rng: random.Random
) -> list[str | None]:
    """One grammar topic per sentence, in proportion to past mistakes.

    A topic's share follows its mistake count, but no topic gets more than
    half of the sentences, so the weakest rule dominates without turning the
    session into a single drill. Once every known topic is at the cap, the
    rest of the level's topics fill the remaining sentences. With no mistake
    history, the level's topics are cycled in random order.
    """
    known = {t: c for t, c in mistake_counts.items() if c > 0}
    if not known:
        pool = list(level_topics)
        if not pool:
            return [None] * count
        rng.shuffle(pool)
        return [pool[i % len(pool)] for i in range(count)]

    total = sum(known.values())
    target = {t: count * c / total for t, c in known.items()}
    cap = max(1, math.ceil(count / 2))
    extras = [t for t in level_topics if t not in known]
    rng.shuffle(extras)

    assigned = {t: 0 for t in known}
    topics: list[str] = []
    extra_turn = 0
    for _ in range(count):
        open_topics = [t for t in known if assigned[t] < cap]
        if open_topics:
            # the topic furthest below its fair share goes next
            pick = max(open_topics, key=lambda t: (target[t] - assigned[t], known[t], t))
        elif extras:
            pick = extras[extra_turn % len(extras)]
            extra_turn += 1
        else:
            pick = max(known, key=lambda t: (known[t], t))  # nothing else to practice
        assigned[pick] = assigned.get(pick, 0) + 1
        topics.append(pick)
    rng.shuffle(topics)
    return topics


def build_slots(
    cards: list[dict],
    stats: dict,
    mistake_counts: dict,
    level_topics: list[str],
    lang: str,
    today: date,
    count: int = DEFAULT_COUNT,
    per_sentence: int = DEFAULT_PER_SENTENCE,
    seed: int | None = None,
) -> list[dict]:
    """The practice plan: for each sentence, target cards and a grammar topic."""
    ranked = rank_cards(cards, stats, today)
    if not ranked:
        raise ValueError("no reviewed vocab cards yet - do a /nachhilfe-vocab session first")

    rng = random.Random(today.toordinal() * 1000 + count if seed is None else seed)

    per_sentence = max(1, per_sentence)
    count = max(1, count)
    if len(ranked) < count * per_sentence:
        # Not enough cards: first use fewer words per sentence, then fewer sentences.
        per_sentence = max(1, len(ranked) // count)
        count = min(count, len(ranked) // per_sentence)
    chosen = ranked[: count * per_sentence]

    verbs = [c for c in chosen if card_kind(c) == "verb"]
    others = [c for c in chosen if card_kind(c) != "verb"]
    slots: list[dict] = []
    for _ in range(count):
        picked: list[dict] = []
        turn = 0
        while len(picked) < per_sentence and (verbs or others):
            first, second = (verbs, others) if turn % 2 == 0 else (others, verbs)
            source = first if first else second
            picked.append(source.pop(0))
            turn += 1
        slots.append({"cards": picked})

    topics = allocate_topics(mistake_counts, level_topics, len(slots), rng)
    rng.shuffle(slots)
    result = []
    for n, (slot, topic) in enumerate(zip(slots, topics), start=1):
        result.append(
            {
                "n": n,
                "cards": [
                    {
                        "id": c["id"],
                        "native_word": c["native_word"],
                        "target_word": c["target_word"],
                        "kind": card_kind(c),
                    }
                    for c in slot["cards"]
                ],
                "grammar_topic": topic,
                "grammar_hint": topic_hint(lang, topic),
            }
        )
    return result


# --------------------------------------------------------------------------
# Validating the model's sentences, checking the learner's answers
# --------------------------------------------------------------------------

def validate_submission(slots: list[dict], submitted, lang: str) -> list[str]:
    """Problems with the sentences the model wrote; empty list = accepted.

    This is the guard against drift: the model is asked for sentences that
    contain specific words and a specific construction, and the code verifies
    it instead of trusting it.
    """
    if not isinstance(submitted, list) or not all(isinstance(x, dict) for x in submitted):
        return ["submission must be a JSON list of objects"]

    by_n: dict[int, dict] = {}
    errors: list[str] = []
    for item in submitted:
        n = item.get("n")
        if n in by_n:
            errors.append(f"sentence {n}: submitted twice")
        by_n[n] = item

    expected = {s["n"] for s in slots}
    for n in sorted(expected - set(by_n)):
        errors.append(f"sentence {n}: missing from submission")
    for n in sorted(set(by_n) - expected, key=str):
        errors.append(f"sentence {n}: not part of this session")

    for slot in slots:
        item = by_n.get(slot["n"])
        if item is None:
            continue
        n = slot["n"]
        source = (item.get("source") or "").strip()
        reference = (item.get("reference") or "").strip()
        if not source:
            errors.append(f"sentence {n}: empty 'source'")
        if not reference:
            errors.append(f"sentence {n}: empty 'reference'")
        if not source or not reference:
            continue
        if normalize(source) == normalize(reference):
            errors.append(f"sentence {n}: 'source' is identical to 'reference' (wrong language?)")

        ref_tokens = tokens(reference)
        src_tokens = set(tokens(source))
        keys = item.get("keys")
        if not isinstance(keys, list):
            errors.append(f"sentence {n}: 'keys' must be a list")
            continue
        slot_ids = {c["id"] for c in slot["cards"]}
        key_ids = [k.get("card_id") for k in keys if isinstance(k, dict)]
        for cid in sorted(slot_ids - set(key_ids)):
            errors.append(f"sentence {n}: no key for target card {cid}")
        for cid in sorted(set(key_ids) - slot_ids, key=str):
            errors.append(f"sentence {n}: key for card {cid} which is not a target of this sentence")
        for key in keys:
            if not isinstance(key, dict) or not key_tokens(key):
                errors.append(f"sentence {n}: every key needs a card_id and a non-empty 'tokens' list")
                continue
            for tok in key_tokens(key):
                if tok not in ref_tokens:
                    errors.append(
                        f"sentence {n}: key token '{tok}' (card {key.get('card_id')}) "
                        "does not appear in 'reference'"
                    )
                if len(tok) >= 6 and tok in src_tokens:
                    errors.append(
                        f"sentence {n}: target word '{tok}' appears in the 'source' sentence (leak)"
                    )
        if marker_found(lang, slot["grammar_topic"], reference) is False:
            errors.append(
                f"sentence {n}: 'reference' shows no marker of the requested grammar topic "
                f"'{slot['grammar_topic']}'"
            )
    return errors


def check_answer(answer: str, sentence: dict, grammar_topic: str | None, lang: str) -> dict:
    """Deterministic comparison of the learner's answer with the reference."""
    exact = tokens(answer) == tokens(sentence["reference"])
    keys = check_keys(sentence["keys"], answer)
    return {
        "exact_match": exact,
        "keys": keys,
        "grammar_marker_found": marker_found(lang, grammar_topic, answer),
        "answer_words": len(tokens(answer)),
    }


def score_out_of_10(verdicts: list[str]) -> float:
    if not verdicts:
        return 0.0
    points = sum(1.0 if v == "correct" else 0.5 if v == "partial" else 0.0 for v in verdicts)
    return round(10 * points / len(verdicts), 1)


def card_outcome(key_result: dict, accepted: set[str]) -> str:
    """hit / spelling / miss for one target word in one answered sentence."""
    if key_result["card_id"] in accepted or key_result["verdict"] == "ok":
        return "hit"
    return "spelling" if key_result["verdict"] == "spelling" else "miss"


def update_stats(stats: dict, card_id: str, outcome: str, today: date) -> None:
    entry = stats.setdefault(card_id, {"seen": 0, "hit": 0, "missed": 0, "spelling": 0})
    entry["seen"] += 1
    entry["last_seen"] = today.isoformat()
    if outcome == "miss":
        entry["missed"] += 1
    else:
        entry["hit"] += 1
        if outcome == "spelling":
            entry["spelling"] = entry.get("spelling", 0) + 1
