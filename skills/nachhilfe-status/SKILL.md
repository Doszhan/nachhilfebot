---
name: nachhilfe-status
description: Show the learner's current progress toward their aim level, current streak, recent sessions, and per-discipline performance (vocabulary mastery breakdown, reading/writing/grammar score trends). Use when the learner asks "how am I doing", "show my progress", "status", "what's my streak", or invokes /nachhilfe-status. Read-only, safe to auto-invoke.
disable-model-invocation: false
---

# nachhilfebot: status

Run:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe status
```

This returns one JSON report with every number already computed. **Render
it exactly as given — do not recompute, round differently, or re-derive any
number yourself.** Your only job here is formatting/presentation.

If it errors because no profile exists yet, tell the learner to run
`/nachhilfe-init` first.

## Layout

1. **Progress toward aim level** — show `progress.bar` verbatim as the
   progress bar, followed by: `"<hours_done> hours done, <hours_left> hours
   left"` (use `progress.hours_done` / `progress.hours_left` exactly).
2. **Streak** — `streak.current` days (mention `streak.longest` too if it's
   different from current, e.g. "current streak: 3 days, best: 12 days").
3. **Last 10 sessions** — table from `last_sessions`: date, type, minutes,
   score. Keep the JSON order (most recent on top); don't show `logged_at`.
4. **Last 10 active days** — table from `active_days`: date, session count,
   total minutes. Keep the JSON order (most recent on top).
5. **Vocabulary mastery** — from `vocab_mastery`: counts for `very_good`,
   `good`, `in_learning`. Directly under the counts, add one explanatory
   line built from `mastery_thresholds`, e.g.: "Very good = FSRS stability
   ≥ {very_good_stability_days} days, good = ≥ {good_stability_days} days,
   in learning = below that or not yet reviewed." Pull the numbers from the
   JSON, never hardcode 21/7 — the learner can change these via
   `/nachhilfe-config`.
6. **Reading** — `reading.average_last_5` (as a %), then the table from
   `reading.history` (each row is either a single date, a week, or a
   month — the `period` field already tells you which; just label the
   column "Date/Week/Month" generically as "Period").
7. **Writing** — same shape as reading, using `writing.average_last_5` and
   `writing.history` (score out of 10, per `RUBRIC.md` at the plugin root).
8. **Grammar** — `grammar.average_last_5`, `grammar.history`, and
   `grammar.weak_topics` (topic name + mistake count) as a short "topics to
   work on" list — mention these are candidates for `/nachhilfe-grammar`'s
   weak-topic mode.

If a discipline has no sessions yet (`average_last_5` is `null`, `history`
is empty), say so plainly rather than showing an empty table.

9. **Available commands** — end every `/nachhilfe-status` report with a
   list of all plugin commands and a one-line description of each:

   - `/nachhilfe-init` — set up or reconfigure a learner profile (native
     language(s), target language, current/aim CEFR level, timeframe).
   - `/nachhilfe-status` — this report: progress, streak, sessions, and
     per-discipline performance.
   - `/nachhilfe-vocab` — FSRS-scheduled vocabulary review/learning
     session (native → target production).
   - `/nachhilfe-writing` — exam-style writing task, graded against the
     shared rubric.
   - `/nachhilfe-reading` — level-appropriate reading text with
     comprehension questions, scored as a percentage.
   - `/nachhilfe-grammar` — grammar practice, either a random topic or one
     targeting past mistakes.
   - `/nachhilfe-config` — view or change settings (hours per level
     transition, FSRS mastery thresholds).
