---
name: nachhilfe-vocab
description: Run a vocabulary review/learning session using FSRS spaced repetition — the learner sees a word in their native language and must produce it in the target language, then gets three example sentences. A valid synonym counts as correct only if the learner agrees. Use only when invoked as /nachhilfe-vocab.
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

   The result also holds `examples` (the card's saved example sentences, empty
   until some were saved), `accepted_synonyms` and `rejected_synonyms` (the
   learner's earlier decisions about synonyms for this card).
3. Judge correctness (accept minor typos and missing articles only if the
   task didn't ask for them) and pick an FSRS rating:
   - **again** — wrong or no recall at all
   - **hard** — correct but with real hesitation or a small but genuine error
   - **good** — correct, normal recall
   - **easy** — correct, instant/confident recall

   **Synonyms: the learner decides, not you.** If the answer is not the card's
   word but is a real German word with the same meaning (not a typo, not a
   related word with another meaning):
   - listed in `accepted_synonyms`: count it as correct (`good`) without asking;
   - listed in `rejected_synonyms`: count it as not matching (`again`) without
     asking, and say that the card wants the card's word;
   - otherwise stop and ask, in one line: "*<their word>* is a valid synonym of
     *<native word>*. Should I mark it as correct? (yes / no)". Wait for the
     answer, then remember it and rate (`yes` = `good`, `no` = `again`):

     ```bash
     PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe vocab-synonym --card-id "<id>" --word "<their word>" --verdict "<accept|reject>"
     ```
4. Apply the rating:

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe vocab-review --card-id "<id>" --rating "<again|hard|good|easy>"
   ```

5. Tell the learner whether they were right, show the correct form if they
   weren't, and show **three example sentences** for the card (below). Then
   move to the next card. Don't editorialize about the FSRS internals
   (stability/difficulty numbers) unless they ask.

### Example sentences (after the answer, never before)

Every card shows three examples: each one a sentence in the target language
with its translation in the language of the card's native word. If
`examples` from `vocab-reveal` is not empty, show those. Otherwise write
three and save them, so the same ones come back at every review (quoted
heredoc, JSON on stdin):

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe vocab-examples --card-id "<id>" <<'JSON'
[
  {"target": "Ich habe eine Beschwerde eingereicht.", "native": "I filed a complaint."},
  {"target": "Die Beschwerde wurde abgelehnt.", "native": "The complaint was rejected."},
  {"target": "Er schreibt eine Beschwerde an den Vermieter.", "native": "He writes a complaint to the landlord."}
]
JSON
```

- Use the card's word in the form the card teaches (nouns with their article
  and the plural in at least one sentence; verbs with `sich` and the
  preposition if they have them).
- Three different situations, natural everyday or work German at the card's
  level, one clause each where possible.
- If the plugin rejects the examples, fix what it names and send all three
  again. If the learner says the examples are poor, rewrite them with
  `--replace`.
- Show them as a short list: the German sentence, the translation below it.
  Skip them only if the learner asks to go faster.

## 5. Retry round (cards rated again or hard)

When the last card is done, re-ask the cards that went badly. The plugin
remembers them — you don't have to track which ones they were:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe vocab-retry-list
```

This returns `{"failed", "fixed", "pending": [{"id", "native_word", "level",
"rating", "attempts"}]}`. If `pending` is empty, skip to step 6. Otherwise tell
the learner in one line that a short retry round follows, then ask every
pending card exactly like in step 4.1 (native word + level, same rules for
nouns and verbs), one at a time.

After each answer:

1. Reveal the answer with `vocab-reveal`, judge it by the same standard as
   before (right word, article/plural for nouns, `sich` and preposition for
   verbs; a synonym follows the saved decisions, and an undecided one is asked
   about, as in step 3), and give one line of feedback. Don't repeat the three
   examples here; show one of the saved ones only if they got it wrong again.
2. Record the outcome:

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe vocab-retry-record --card-id "<id>" --result "<correct|wrong>"
   ```

**Never call `vocab-review` during the retry round.** This is a short memory
rewind, not a new review: it must not change any card's schedule.

When every pending card has been asked, run `vocab-retry-list` again. Cards
answered wrong are offered once more (the plugin allows at most two attempts
per card); keep going until `pending` is empty. Then mention in the session
summary how many cards the retry round fixed (`fixed` out of `failed`, as
reported by the last `vocab-retry-list`) and name the ones that are still
shaky. If the learner asks to skip the retry round, skip it.

## 6. Log the session

Estimate the session's duration in minutes (a reasonable estimate based on
number of cards and pace, including the retry round — a few minutes for a
handful of cards, more for 15+), then:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe session-log --type vocab --minutes <N>
```

Vocab sessions don't carry a single "score" the way writing/reading do
(FSRS already captured per-card performance) — leave `--score` unset.
