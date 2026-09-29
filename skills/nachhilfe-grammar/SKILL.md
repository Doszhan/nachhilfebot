---
name: nachhilfe-grammar
description: Run a grammar practice session, either on a random topic at the learner's level or targeting a topic they've struggled with in past writing/reading/grammar sessions. Use only when invoked as /nachhilfe-grammar.
disable-model-invocation: true
---

# nachhilfebot: grammar

## 1. Read standing preferences

```bash
LANG_DIR=$(PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe paths | python3 -c "import json,sys; print(json.load(sys.stdin)['lang_dir'])")
cat "$LANG_DIR/CUSTOM_PROMPTS.md"
```

## 2. Ask the learner: random topic, or work on a weak spot?

Offer both, unless they already said which in their invocation message.

**Random topic at their level:**

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe grammar-topics
```

Pick one at random from the list yourself.

**Weak topic (most mistakes tagged across past sessions):**

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe grammar-weak
```

Returns `[[topic, mistake_count], ...]`, ranked worst-first. Pick the top
one, or let the learner choose among the top few. If it's empty, fall back
to a random topic and say why.

## 3. Run the session

Give a short explanation of the rule if useful, then plan a set of
exercises (fill-in-the-blank, transform-the-sentence, translate-the-sentence
— mix it up) targeting that specific topic, calibrated to the learner's
level.

**Present exercises one at a time, not as a batch.** After the rule
explanation, show only the first exercise and end your message right there
(a line like **Type your answer:**) — no answer key, no preview of the rest
of the set below it. Wait for the learner's answer, give brief feedback on
that one item, then show the next exercise the same way. Repeat until the
planned set is done, then grade the whole session per below.

Score using the same rubric as writing (`RUBRIC.md` at the plugin root),
out of 10 — task fulfillment/accuracy is really "did they use the target
structure correctly," vocabulary/coherence sub-scores still apply if
exercises involve full sentences.

## 4. Log the session

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe session-log \
  --type grammar --minutes <your time estimate> --score <total /10> \
  --topic "<the grammar topic practiced>" \
  --mistake "<the same topic string, if they still made errors in it>"
```

Tag `--mistake` with the exact topic string being practiced if they made
any errors in it during the session — this feeds back into
`grammar-weak` so a topic that's actually improving eventually drops out of
the weak-topic ranking as mistake counts elsewhere in the deck accumulate
relative to it. (Counts are cumulative, not decayed — a topic that used to
be weak and is now solid will still show old mistakes; mention this if the
learner asks why a topic they've since mastered is still listed.)

Estimate `--minutes` based on the number and complexity of exercises.
