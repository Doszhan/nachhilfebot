---
name: nachhilfe-writing
description: Give the learner an exam-style writing task (formal email, informal message, opinion piece, etc.) calibrated to their target level, then grade their submission against the shared rubric. Use only when invoked as /nachhilfe-writing.
disable-model-invocation: true
---

# nachhilfebot: writing

## 1. Read standing preferences

```bash
LANG_DIR=$(PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe paths | python3 -c "import json,sys; print(json.load(sys.stdin)['lang_dir'])")
cat "$LANG_DIR/CUSTOM_PROMPTS.md"
```

Apply any relevant standing preferences (topic interests, register, task
type preferences). If the learner passed inline customization after the
`/nachhilfe-writing` command itself (e.g. "please make it about the Berlin
rental market"), that's a one-off for this session only — don't write it to
`CUSTOM_PROMPTS.md` unless they explicitly ask you to remember it.

## 2. Pick a task

Get the learner's level and avoid repeating a topic they've already had:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe config-get --file profile
```

`writing.json` under the language's data directory has a `used_topics`
list — check it (via the `cat "$LANG_DIR/writing.json"` command, this file
is small and this is the one case where reading a DB file directly is fine
since it's just a short topic list, not the growing session log) and avoid
repeats. Give a task in the style of a real exam for that CEFR level (e.g.
for German: formal email/Beschwerdebrief at B1+, informal message at A2+,
opinion essay at B2+) — task type, register, and a **specific target word
count range** appropriate to the level and task type (e.g. "40–60 words"
for an A2 informal message, "150–200 words" for a B2 opinion essay). State
that range explicitly in the task instructions — it's graded against
afterward, not just a vague "keep it short/long."

## 3. Collect the submission, then grade it

First, count the submitted words — don't eyeball this, compute it. Pipe
the learner's exact submitted text through a quoted heredoc (quoting
`'EOF'` keeps the shell from interpreting anything inside, so it's safe
even if the text contains quotes, `$`, or backticks):

```bash
wc -w <<'EOF'
<the learner's exact submitted text, verbatim>
EOF
```

Then grade it using the rubric in `RUBRIC.md` at the plugin root
(`${CLAUDE_PLUGIN_ROOT}/RUBRIC.md`) — four sub-scores (task fulfillment /3,
grammatical accuracy /3, vocabulary range /2, coherence /2) summing to a
score out of 10. Show:

- **Word count**: `"Submitted: <count from wc -w> words (target: <range you gave>)"`,
  right after the score — use the exact number `wc -w` printed, never a
  recount-by-eye.
- Each sub-score with a one-line reason.
- The specific mistakes found, each tagged with the exact grammar-topic
  string for this level:

  ```bash
  PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe grammar-topics
  ```

  Match each mistake to the closest topic in that list — this keeps
  mistake tags consistent so `/nachhilfe-grammar`'s weak-topic mode works.
- A corrected version of anything that was wrong.
- The total score out of 10.

## 4. Log the session

```bash
LANG_DIR=$(PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe paths | python3 -c "import json,sys; print(json.load(sys.stdin)['lang_dir'])")
python3 - <<'PY'
import json, os
path = os.path.join(os.environ["LANG_DIR"], "writing.json")
with open(path) as f:
    data = json.load(f)
data["used_topics"].append("<the task topic you gave>")
with open(path, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY

PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe session-log \
  --type writing --minutes <your time estimate> --score <total /10> \
  --topic "<task topic>" \
  --mistake "<grammar topic tag>" --mistake "<another tag>" ...
```

Only the topic, score, minutes, and mistake tags are persisted — not the
learner's full submitted text or your corrections, to keep the local
database small and avoid storing potentially sensitive writing content
long-term. If they ask you to keep the full text somewhere, that's a
one-off file they manage themselves, not something this plugin stores.

Estimate `--minutes` yourself based on task length and complexity — this is
the one place session duration is a judgment call rather than a measured
value.
