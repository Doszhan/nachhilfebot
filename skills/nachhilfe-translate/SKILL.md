---
name: nachhilfe-translate
description: Run a translation session — sentences in the learner's native language that they translate into the target language. The plugin picks the words and grammar topics the learner fails most, checks the sentences you write, and matches the learner's answers against the required words. Use only when invoked as /nachhilfe-translate.
disable-model-invocation: true
---

# nachhilfebot: translate

The learner translates sentences from their native language into the target
language. **The plugin decides what to practice and checks the result; you
only write the sentences, judge answers that differ from the reference, and
explain.** Use the commands below for every number and every decision they
cover — never choose target words or topics yourself, never recompute the
score.

## 1. Read standing preferences

```bash
LANG_DIR=$(PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe paths | python3 -c "import json,sys; print(json.load(sys.stdin)['lang_dir'])")
cat "$LANG_DIR/CUSTOM_PROMPTS.md"
```

Apply anything relevant (topics of interest, register) to the *content* of
the sentences.

## 2. Plan the session

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe translate-start
```

The session size is fixed in code (5 sentences) — do not pass `--count`, even
if the learner's message suggests another number. Optional flag:
`--source-language "<language>"` (the language the sentences are written in;
the default is saved with `translate-config --source-language "<language>"`,
otherwise the first native language in the profile).

The result is `{"resumed", "source_language", "level", "slots": [...]}`. Each
slot has a number `n`, the `cards` the sentence must exercise (`native_word`,
`target_word`, `kind`) and a `grammar_topic` with a `grammar_hint`. The
plugin picked them from the learner's lapses (again/hard ratings), earlier
translation misses and grammar mistake counts.

- If it fails with "no reviewed vocab cards yet", tell the learner to run
  `/nachhilfe-vocab` first.
- If `resumed` is true, say that you are continuing today's open session; if
  `sentences_submitted` is also true, skip step 3 and go to step 4.
- Do not tell the learner which words or topics were chosen; that would turn
  the exercise into a fill-in.

Also fetch the grammar tags you will need for step 4:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe grammar-topics
```

## 3. Write the sentences

For **every** slot write one sentence in `source_language` plus its correct
translation. Requirements:

- **Level:** natural, everyday or work-related, matching `level` (at B1/B2
  roughly 10–20 words; one or two clauses).
- **Target words:** the German translation must naturally use each of the
  slot's `target_word`s, in the form the card teaches — with the reflexive
  pronoun and preposition for verbs, with article and the right number for
  nouns. Express the *meaning* of the card's `native_word`; never put the
  German word itself in the source sentence.
- **Grammar:** if the slot has a `grammar_hint`, the translation must contain
  that construction (the plugin verifies typical markers and rejects the
  sentence if they are missing).
- **One clear best translation:** avoid idioms and phrasing with many equally
  good renderings, so the answer can be compared reliably.
- Use the vocabulary the learner already has at that level for everything
  else, so the target words and the grammar are what is being tested.

Submit all sentences at once as JSON on stdin (quoted heredoc so quotes and
umlauts survive):

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe translate-submit <<'EOF'
[
  {
    "n": 1,
    "source": "Хотя идёт дождь, я увлекаюсь фотографией.",
    "reference": "Obwohl es regnet, begeistere ich mich für Fotografie.",
    "keys": [
      {"card_id": "<id of the card>", "tokens": ["begeistere", "mich", "für"]}
    ]
  }
]
EOF
```

`keys` has one entry per target card of the slot. `tokens` are the words of
your `reference` that carry that card **exactly as written there**: for a
verb the conjugated form plus reflexive pronoun, separable particle and
preposition; for a noun the noun and its article. They are what the learner's
answer is checked against, so they must all occur in `reference`.

If the plugin rejects the submission it lists every problem (missing key,
token not in the reference, construction not visible, target word leaked into
the source). Fix those and resubmit **all** sentences.

## 4. Run the exercise

Repeat until the plugin says `done`:

1. Get the next sentence:

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe translate-next
   ```

   Show only `n`/`total` and `source`, and ask the learner to translate it
   into the target language. Don't show the reference or hints about words
   or grammar.

2. After they answer, check it (pass their answer verbatim through a quoted
   heredoc):

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe translate-check --n <N> <<'EOF'
   <the learner's answer, verbatim>
   EOF
   ```

3. Read the result:
   - `exact_match: true` (`verdict_recorded: true`): correct, already
     recorded. Confirm it, show the reference, move on. Don't grade it again.
   - Otherwise compare `reference` and the answer yourself, guided by the
     computed facts:
     - `keys[].tokens[].status`: `missing` = the word is not in the answer (a
       missing `für`/`auf` means a wrong or missing preposition, a missing
       `mich`/`sich` a missing reflexive pronoun); `similar` = a close word
       (`found`), either a typo or a different ending; `umlaut` = same letters
       but umlaut/ß spelled differently; `exact` = fine.
     - `grammar_marker_found: false` = no typical marker of the requested
       construction was found, so the learner may have avoided it. Say so if
       it is true for their answer.
   - Decide the verdict: `correct` (meaning and grammar right, even if worded
     differently), `partial` (understandable, with errors or a target word
     missing/misspelled), `wrong` (meaning lost or serious errors).
   - Tag every grammar mistake with the **exact** topic string from
     `grammar-topics` (run `grammar-topics --level <A2|A1>` for a basic
     topic), one `--mistake` per error. Spelling and vocabulary slips need no
     tag.
   - If the learner used an equally valid expression instead of a target
     word, pass `--accept <card_id>` for that card.

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe translate-record --n <N> --verdict "<correct|partial|wrong>" \
     --mistake "<exact grammar topic>" --accept "<card id>"
   ```

   The plugin refuses `correct` while a target word is missing or misspelled,
   or together with mistake tags. Follow its message instead of arguing with it.

4. Give short feedback in the target language (with source-language glosses
   where that helps): show the reference, quote what was wrong in the
   learner's answer, and state the rule or the correct form in one line. Base
   it on what the check reported; don't invent errors.

## 5. Finish and log

Estimate the duration in minutes (about 1.5–2 minutes per sentence), then:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe translate-finish --minutes <N>
```

(Add `--allow-partial` if the learner stopped early; only answered sentences
count.) The plugin computes the score out of 10 as
`(correct + 0.5 × partial) / answered × 10`, updates the per-word statistics
that steer the next session, logs the session, and adds the mistake tags to
the grammar mistake counts.

Show the learner, from the result and without recomputing anything:

- the score and the correct / partial / wrong counts;
- `vocab_missed` (words they could not produce) and `vocab_spelling` (words
  they spelled wrongly), by `target_word`;
- `grammar_mistakes` and `construction_possibly_avoided`;
- one or two concrete suggestions (e.g. a verb–preposition pair to write
  their own sentence with, or `/nachhilfe-grammar` on the weakest topic).

Missed words and weak topics are prioritized automatically in the next
`/nachhilfe-translate` session.
