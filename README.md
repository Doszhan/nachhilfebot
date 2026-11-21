# nachhilfebot

A Claude Code plugin for learning a language. Python handles scheduling,
scoring and progress, so the LLM only teaches and gives feedback, with short
prompts and less drift.

It offers FSRS-scheduled vocabulary drills (with an end-of-session retry
round), exam-style writing/reading/grammar practice, translation exercises
built around your weakest words and grammar topics, real-life dialog practice
with a random everyday situation, and a progress dashboard. Every number
(streaks, hour totals, FSRS scheduling, score averages) is computed by a
small vendored Python backend instead of estimated by the model, and each
command's prompt stays short so the model stays focused on what only it can
do: writing tasks, explanations, and feedback on your language. See
`RUBRIC.md` for the scoring rubric of every exercise.

## Install

```
claude plugin marketplace add doszhan/nachhilfebot
claude plugin install nachhilfebot@doszhan
```

Then restart Claude Code (or run `/reload-plugins`).

Requires [Claude Code](https://claude.com/claude-code) and a system
`python3` (3.10+) — no `pip install` step, FSRS is vendored in pure Python
stdlib (`scripts/nachhilfe/fsrs.py`).

**Update:** `claude plugin marketplace update doszhan`, then
`claude plugin update nachhilfebot@doszhan`.

**Uninstall:** `claude plugin uninstall nachhilfebot@doszhan`.
Your learning data is never touched — it lives in your own folder (see
[Your data](#your-data)).

### Quick start

Your progress is stored in the folder you start Claude Code from, so pick a
dedicated one and always start from there:

```
mkdir ~/german && cd ~/german
claude
```

Then run `/nachhilfe-init` and answer the questions, followed by
`/nachhilfe-vocab` for your first session.

To install from a local clone instead of GitHub, pass its path:
`claude plugin marketplace add /path/to/nachhilfebot`.

## Commands

| Command | What it does |
|---|---|
| `/nachhilfe-init` | Set up your profile: native/target language, current & aim CEFR level, timeframe. |
| `/nachhilfe-status` | Progress bar to your aim level with a line chart of your total study hours since day one, streak, recent sessions, vocab mastery breakdown, reading/writing/grammar/translate/dialog score trends. |
| `/nachhilfe-vocab` | FSRS-scheduled vocabulary review (native language → target language). After each answer you see three example sentences (target language with a translation); they are saved on the card, so the same ones come back. If you answer with a synonym, you decide whether it counts as correct, and the plugin remembers your decision for that card. Words you got wrong or only barely right are asked again at the end of the session; that retry round never changes the schedule. |
| `/nachhilfe-vocab-edit-native` | Pick one of your latest cards and change its native-language word (for example a vague or wrong translation). The target word and the schedule stay as they are. |
| `/nachhilfe-writing` | Exam-style writing task, graded against `RUBRIC.md`. |
| `/nachhilfe-reading` | Level-appropriate reading text with comprehension questions, scored as % correct. |
| `/nachhilfe-grammar` | Practice a random topic at your level, or your weakest topic by mistake count. |
| `/nachhilfe-translate` | Translate sentences from your native language into the target language. The plugin picks the words and grammar topics you fail most; code validates the sentences, matches your answers against the required words and caps the grade it can give. Every sentence is graded 0-10, the session score is the average. |
| `/nachhilfe-dialog` | Real-life conversation practice with no fixed scenarios: the bot invents a fresh everyday situation and its characters every time (nudged by a random area of life, never repeating a recent one), plays the other person and speaks first. You answer short and direct and may ask questions too; sometimes something unexpected happens. Each answer is corrected right away and graded 0-10 from three sub-scores. |
| `/nachhilfe-config` | Edit hour-per-level-transition estimates or FSRS mastery thresholds. |

If a bare `/nachhilfe-init` doesn't resolve on your Claude Code version,
use the fully-qualified `/nachhilfebot:nachhilfe-init` form instead.

Every command besides `/nachhilfe-status` is explicit-invocation-only
(`disable-model-invocation: true`) — the model won't start a quiz or
writing task on its own initiative.

## Your data

Everything is stored locally under `<cwd>/nachhilfe/<target-language>/`,
where `<cwd>` is always the directory you're in when you run a
`/nachhilfe-*` command — resolved fresh every time, with no global pointer
file. Running commands from a different directory means different (or
missing) data; there's no cross-directory memory by design.

```
<data_dir>/nachhilfe/
  config.json                  # which language is currently active
  <lang>/
    profile.json                 # native/target language, levels, target date
    status.json                   # append-only session log (all types)
    vocab.json                     # FSRS card states, saved example sentences, synonym decisions
    vocab-session.json              # today's retry list (exists only during a vocab session)
    translate.json                   # per-word translate stats and the translate source language
    translate-session.json            # the open translate session (deleted when it is finished)
    dialog.json                        # titles of the situations you played lately (so they don't repeat)
    dialog-session.json                 # the open dialog: situation title, surprise plan, grades (deleted when finished)
    reading.json / writing.json     # rubric version + topics already used
    grammar.json                     # grammar topic taxonomy + mistake counts
    level-hours.json                  # hours needed per CEFR transition (editable)
    mastery-thresholds.json            # FSRS stability cutoffs (editable)
    CUSTOM_PROMPTS.md                   # your standing preferences
```

If `<data_dir>` turns out to be inside a git repo, `/nachhilfe-init` flags
it — add `nachhilfe/` to that repo's `.gitignore` unless you actually want
your learning history committed there.

Writing/reading sessions store the topic, score, and minutes — not the full
submitted text or generated content — to keep the database small and avoid
retaining potentially sensitive writing long-term. Translate sessions keep
your typed answers only while the session is open; `translate-finish` deletes
them and keeps just the score, the mistake tags and per-word hit/miss counts.
Dialog sessions never store what you or the bot said, only the situation, the
grade of each answer and the mistake tags.

## Privacy

Everything stays on your machine: no network requests, no telemetry. See
[PRIVACY.md](PRIVACY.md) for what the plugin stores and runs.

## Translate and retry: how code and model split the work

Both features follow the same rule: **code decides and verifies, the model
writes and explains.**

* **Retry round** (`/nachhilfe-vocab`): the plugin records every card rated
  `again`/`hard`, hands the list back after the last card, caps retries at two
  attempts per card, and refuses to touch FSRS state while doing so.
* **Translate** (`/nachhilfe-translate`): the plugin ranks your cards by
  lapses (again/hard ratings), earlier translation misses and FSRS stability, and
  your grammar topics by mistake count (at most half of a session on one
  topic), then plans each sentence. The model writes the sentences and the
  reference translations; the plugin rejects them unless every target word
  occurs in the reference and the requested construction is visible. Your
  answer is matched word by word against the required words (exact / umlaut /
  similar / missing), which pinpoints wrong prepositions, missing reflexive
  pronouns and misspellings without a model. The model judges whatever the
  matching can't (alternative wording, grammar errors) inside guard rails:
  every sentence gets a grade from 0 to 10, but the plugin caps it at 7 while
  a target word is missing and at 9 while one is misspelled or the answer
  carries mistake tags, and mistake tags must be exact grammar-topic strings.
  The session score and statistics are computed in code.
* **Dialog** (`/nachhilfe-dialog`): there is no scenario list. The model
  invents the situation, the people, their mood and any surprise afresh for
  every dialog. The plugin only keeps it varied and honest: it gives a random
  area-of-life nudge (otherwise models repeat the same few situations),
  remembers the situation titles played lately and rejects a repeat, plans
  whether and after which answer a surprise happens, and validates the mistake
  tags. The model corrects each answer right after it, and grades it from
  three sub-scores (fit 0-4, accuracy 0-3, naturalness 0-3); the plugin adds
  them up and averages the session.

## Design principles

1. **Determinism over LLM judgment wherever the answer is computable.**
   Streaks, hour totals, FSRS scheduling, and averages are all Python, not
   model estimation. The model's only numeric judgment calls are grading
   free-text answers and session-time estimates.
2. **Skills never read/write the JSON databases directly** (except the
   small `used_topics` lists and `CUSTOM_PROMPTS.md`) — everything goes
   through `python3 -m nachhilfe <command>`, which returns only the slice
   of data a skill needs. This is what keeps context small and prevents
   drift as history grows over months.
3. **Zero required external dependencies** — FSRS is vendored, not pulled
   from PyPI.

## Development

```bash
cd scripts
PYTHONPATH=. python3 -m nachhilfe --help
```

### Tests

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest tests/
```

Covers `fsrs.py` (FSRS state transitions, rating ordering, mastery
buckets), `progress.py` (streaks, hour math, rolling averages, score
rollups), `retry.py` (retry list rules), `vocab.py` (recent cards, native-word edits, example
sentences, synonym decisions), `translate.py` (target selection,
sentence validation, answer matching, score ceilings), `dialog.py` (variety
nudge, surprise plan, per-answer grading), and a round-trip `db.py`/`cli.py` integration test that `chdir`s
into a temp directory (the data root always resolves to `<cwd>/nachhilfe`)
— never touches your real data location.
