# nachhilfebot

A Claude Code plugin for learning a language. Python handles scheduling,
scoring and progress, so the LLM only teaches and gives feedback, with short
prompts and less drift.

It offers FSRS-scheduled vocabulary drills, exam-style
writing/reading/grammar practice, and a progress dashboard. Every number
(streaks, hour totals, FSRS scheduling, score averages) is computed by a
small vendored Python backend instead of estimated by the model, and each
command's prompt stays short so the model stays focused on what only it can
do: writing tasks, explanations, and feedback on your language. See
`RUBRIC.md` for the writing/grammar scoring rubric.

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
| `/nachhilfe-status` | Progress bar to your aim level, streak, recent sessions, vocab mastery breakdown, reading/writing/grammar score trends. |
| `/nachhilfe-vocab` | FSRS-scheduled vocabulary review (native language → target language). |
| `/nachhilfe-writing` | Exam-style writing task, graded against `RUBRIC.md`. |
| `/nachhilfe-reading` | Level-appropriate reading text with comprehension questions, scored as % correct. |
| `/nachhilfe-grammar` | Practice a random topic at your level, or your weakest topic by mistake count. |
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
    vocab.json                     # FSRS card states
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
retaining potentially sensitive writing long-term.

## Privacy

Everything stays on your machine: no network requests, no telemetry. See
[PRIVACY.md](PRIVACY.md) for what the plugin stores and runs.

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
rollups), and a round-trip `db.py`/`cli.py` integration test that `chdir`s
into a temp directory (the data root always resolves to `<cwd>/nachhilfe`)
— never touches your real data location.
