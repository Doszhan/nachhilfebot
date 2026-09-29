---
name: nachhilfe-vocab
description: Run a vocabulary review/learning session using FSRS spaced repetition — the learner sees a word in their native language and must produce it in the target language. Use only when invoked as /nachhilfe-vocab.
disable-model-invocation: true
---

# nachhilfebot: vocab

## 1. Read standing preferences

```bash
LANG_DIR=$(PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe paths | python3 -c "import json,sys; print(json.load(sys.stdin)['lang_dir'])")
cat "$LANG_DIR/CUSTOM_PROMPTS.md"
```

Apply anything relevant found there (topic preferences, register, etc.) to
word choice for this session.

## 2. Get due cards

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe vocab-due --limit 15
```

Each item is `{"id", "native_word", "level"}` — the target-language answer
is deliberately withheld so you can't leak it before the learner answers.

## 3. Top up with new words if the due queue is short

If the queue has fewer than ~10 cards, add new level-appropriate vocabulary
(matching the learner's current level from their profile) until there are
enough for a session (10–15 total is a good session size, fewer if the
learner asked for a quick session). Before adding, check for duplicates:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe vocab-words
```

This lists existing native-language words already in the deck — pick new
words not already on that list. Add each one:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe vocab-add \
  --native-word "<word/phrase in learner's native language>" \
  --target-word "<correct target-language translation>" \
  --level "<CEFR level of this word>"
```

Newly added cards are immediately due (state "new"), so re-run `vocab-due`
afterward, or just include them yourself in the session directly.

## 4. Run the session

For each card, one at a time:

1. Show the learner the native-language word **and its CEFR level**
   (from the card's `level` field, e.g. "[B1]") and ask them to translate
   it into the target language. Always this direction (native → target),
   never the reverse. For noun cards, also ask the learner to give the
   article (der/die/das) and both singular and plural forms, not just the
   base word. For verb cards, ask for a bare translation only — never hint
   in the prompt that the verb is reflexive or takes a preposition. The
   learner's answer is still expected to include the reflexive pronoun
   (e.g. "sich") if the verb is reflexive, and the connecting preposition
   if the verb takes one — grade a missing reflexive pronoun or
   preposition as a genuine error, not just a typo-level slip.
2. After they answer, reveal the correct answer to grade against:

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe vocab-reveal --card-id "<id>"
   ```

3. Judge correctness (accept minor typos, missing articles only if the
   task didn't ask for them, valid synonyms) and pick an FSRS rating:
   - **again** — wrong or no recall at all
   - **hard** — correct but with real hesitation or a small but genuine error
   - **good** — correct, normal recall
   - **easy** — correct, instant/confident recall
4. Apply it:

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe vocab-review --card-id "<id>" --rating "<again|hard|good|easy>"
   ```

5. Tell the learner whether they were right, show the correct form if they
   weren't, and move to the next card. Don't editorialize about the FSRS
   internals (stability/difficulty numbers) unless they ask. Whenever the
   learner answers a card incorrectly, also show a correct example
   sentence using the target word before moving to the next card.

## 5. Log the session

Estimate the session's duration in minutes (a reasonable estimate based on
number of cards and pace — a few minutes for a handful of cards, more for
15+), then:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe session-log --type vocab --minutes <N>
```

Vocab sessions don't carry a single "score" the way writing/reading do
(FSRS already captured per-card performance) — leave `--score` unset.
