---
name: nachhilfe-reading
description: Give the learner a level-appropriate reading text, then ask comprehension questions about it and score the results as a percentage correct. Use only when invoked as /nachhilfe-reading.
disable-model-invocation: true
---

# nachhilfebot: reading

## 1. Read standing preferences

```bash
LANG_DIR=$(PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe paths | python3 -c "import json,sys; print(json.load(sys.stdin)['lang_dir'])")
cat "$LANG_DIR/CUSTOM_PROMPTS.md"
```

Same rule as writing: apply standing preferences; treat any inline
customization in the invocation itself as one-off unless asked to remember
it.

## 2. Pick a text

Get the learner's level:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe config-get --file profile
```

Check `$LANG_DIR/reading.json`'s `used_topics` list (direct read is fine —
it's a short list, not the growing session log) and avoid repeating a
recent topic. Write a text calibrated to the level (length, vocabulary,
and sentence complexity appropriate to exam-style reading passages for that
CEFR level), then prepare a set of comprehension questions about it (mix of
factual and inferential, exam-style — e.g. true/false/not-stated, short
answer, multiple choice).

Show the full text once, up front. Then ask the questions **one at a
time**: post a single question and stop, waiting for the learner's answer
before posting the next one. Don't reveal the answer to a question, or any
other question, while waiting for a response. Once the learner has
answered all questions, move to grading.

## 3. Grade the answers

After the last question has been answered, grade each question
right/wrong (partial credit only for genuinely multi-part questions —
count sub-parts). Then compute the percentage exactly, don't estimate it:

```bash
python3 -c "print(round(<correct> / <total> * 100, 1))"
```

Show which questions were right/wrong with brief explanations for the
wrong ones, referencing the text.

## 4. Log the session

```bash
LANG_DIR=$(PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe paths | python3 -c "import json,sys; print(json.load(sys.stdin)['lang_dir'])")
python3 - <<'PY'
import json, os
path = os.path.join(os.environ["LANG_DIR"], "reading.json")
with open(path) as f:
    data = json.load(f)
data["used_topics"].append("<the text's topic>")
with open(path, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY

PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe session-log \
  --type reading --minutes <your time estimate> --score <percent correct> \
  --topic "<text topic>"
```

Only the topic, score, and minutes are persisted — not the reading text
itself or the Q&A, to keep the local database small.

Estimate `--minutes` based on text length and number of questions.
