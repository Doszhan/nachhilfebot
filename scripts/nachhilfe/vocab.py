"""Pure helpers for vocab cards: recent words, native-word edits, example
sentences and the learner's decisions about synonyms.

Nothing here reads or writes files; `cli.py` does the persistence. The
model writes the example sentences, the code checks their shape and stores
them, so the same three sentences come back on every later review.
"""
from __future__ import annotations

EXAMPLES_PER_CARD = 3
RECENT_DEFAULT = 10


def _key(text: str) -> str:
    return " ".join(text.split()).casefold()


def recency(card: dict) -> str:
    """Sort key: when the card was last touched (reviewed, else created)."""
    if card.get("last_reviewed_at"):
        return card["last_reviewed_at"]
    if card.get("last_review"):
        return card["last_review"] + "T00:00:00"
    return (card.get("created_at") or "") + "T00:00:00"


def recent_cards(cards: list[dict], limit: int = RECENT_DEFAULT) -> list[dict]:
    """Most recently reviewed or added cards first (hidden cards left out).

    Within a day the order is exact for cards reviewed since `last_reviewed_at`
    was introduced; older ones fall back to their position in the deck.
    """
    indexed = [(i, c) for i, c in enumerate(cards) if not c.get("suppressed")]
    indexed.sort(key=lambda p: (recency(p[1]), p[0]), reverse=True)
    return [c for _, c in indexed[:limit]]


def duplicate_native(cards: list[dict], native_word: str, exclude_id: str) -> dict | None:
    """Another visible card that already uses this native word."""
    wanted = _key(native_word)
    for c in cards:
        if c["id"] != exclude_id and not c.get("suppressed") and _key(c["native_word"]) == wanted:
            return c
    return None


def check_examples(raw) -> tuple[list[dict] | None, str | None]:
    """Validate the model's example sentences: exactly three {target, native} pairs.

    Returns (clean list, None) or (None, what is wrong).
    """
    if not isinstance(raw, list) or len(raw) != EXAMPLES_PER_CARD:
        return None, f"Expected a JSON list of exactly {EXAMPLES_PER_CARD} examples."
    clean, seen = [], set()
    for n, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            return None, f"Example {n} must be an object with 'target' and 'native'."
        target = " ".join(str(item.get("target", "")).split())
        native = " ".join(str(item.get("native", "")).split())
        if not target or not native:
            return None, f"Example {n} needs both a non-empty 'target' and 'native' sentence."
        if _key(target) == _key(native):
            return None, f"Example {n}: the translation must differ from the target sentence."
        if _key(target) in seen:
            return None, f"Example {n} repeats an earlier sentence."
        seen.add(_key(target))
        clean.append({"target": target, "native": native})
    return clean, None


def synonym_lists(card: dict) -> dict:
    syn = card.get("synonyms") or {}
    return {"accepted": list(syn.get("accepted", [])), "rejected": list(syn.get("rejected", []))}


def record_synonym(card: dict, word: str, accepted: bool) -> dict:
    """Remember the learner's decision about a synonym; a new decision replaces an old one."""
    key = " ".join(word.split())
    lists = synonym_lists(card)
    for name in ("accepted", "rejected"):
        lists[name] = [w for w in lists[name] if _key(w) != _key(key)]
    lists["accepted" if accepted else "rejected"].append(key)
    card["synonyms"] = lists
    return lists
