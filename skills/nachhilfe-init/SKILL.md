---
name: nachhilfe-init
description: Set up a new nachhilfebot learner profile — native language(s), target language, current CEFR level, aim level, and timeframe — and initialize the local databases. Use when the learner wants to start using nachhilfebot for the first time, or wants to (re)configure a target language. Only invoke when the user explicitly asks for it or runs /nachhilfe-init.
disable-model-invocation: true
---

# nachhilfebot: init

Ask the learner the following questions, in this order. Ask them one at a
time (don't dump all five at once) unless the learner has clearly already
answered several in their invocation message.

1. **Native language(s)?** (accept multiple, comma-separated)
2. **Target language?** (the language they want to learn — get an ISO
   639-1 code, e.g. "de" for German, "fr" for French; if they name a
   language in words, map it yourself)
3. **Current level?** A1, A2, B1, B2, C1, C2 — or "0" if they are an
   absolute beginner with no prior exposure.
4. **Aim level?** Must be higher than the current level.
5. **Timeframe to reach the aim level?** Weeks, months, or years.

## Compute the target date

Convert the timeframe answer into an absolute `YYYY-MM-DD` date with a
one-line Python command — don't do this arithmetic yourself:

```bash
# weeks:
python3 -c "from datetime import date, timedelta; print((date.today() + timedelta(weeks=N)).isoformat())"
# months (approximate, 30 days/month):
python3 -c "from datetime import date, timedelta; print((date.today() + timedelta(days=N*30)).isoformat())"
# years:
python3 -c "from datetime import date, timedelta; print((date.today() + timedelta(days=N*365)).isoformat())"
```

Replace `N` with the number the learner gave.

## Run init

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe init \
  --native "<comma-separated native languages>" \
  --target-language "<target language code>" \
  --current-level "<0|A1|A2|B1|B2|C1|C2>" \
  --aim-level "<A1|A2|B1|B2|C1|C2>" \
  --target-date "<YYYY-MM-DD>"
```

Data always lives at `nachhilfe/` under whatever directory this Bash
command happens to run in — **the current working directory, every time**,
with no global pointer file and no cross-directory memory. Running
`/nachhilfe-init` (or any other `/nachhilfe-*` command) from a different
folder means different — or missing — data. This is intentional: the
learner explicitly asked for data to always resolve relative to wherever
they're currently working, in favor of a location that's the same no
matter where a session is launched from. Flag this tradeoff plainly if
it looks like the learner is about to run this from an unfamiliar
directory and may not realize a new, empty profile will result.

This prints the created profile as JSON, including `daily_minutes_target`
(computed assuming 6 practice days/week — 1 rest day), `hours_needed_total`,
`data_dir` (the resolved absolute path data lives under, always
`<cwd>/nachhilfe`), `data_dir_already_configured` (false if this directory
had no `nachhilfe/` folder yet), and `data_dir_in_git_repo`.

**If a profile already exists for this target language**, running init
again updates the level/aim/target-date fields but does **not** erase
vocab cards, session history, or custom prompts — it's safe to re-run to
adjust goals.

## Report back to the learner

State plainly, using the numbers from the JSON output (don't recompute
them):

- Their target: current level → aim level, by the target date.
- Required daily practice: `daily_minutes_target` minutes/day, 6 days/week.
- Total hours needed for this stretch: `hours_needed_total`.
- **Only if `data_dir_already_configured` was `false`** (first-ever init):
  tell them plainly where their data now lives (`data_dir`), and that this
  location is now permanent — reinstalling or updating the plugin won't
  move it, but nothing here will move it either if they later wish they'd
  picked somewhere else (they'd need to manually delete
  `~/.config/nachhilfebot/location.json` and start over, losing nothing
  already on disk, before their next init). If `data_dir_in_git_repo` is
  `true`, tell them clearly to add `nachhilfe/` to that repo's
  `.gitignore` unless they actually want their learning history committed.
- That default level-hour estimates and FSRS mastery thresholds can be
  changed later via `/nachhilfe-config`, and that a
  `CUSTOM_PROMPTS.md` file was created for standing preferences (topics
  they like, register preferences, etc.) — mention they can just say
  "remember that I prefer informal writing tasks" any time and future
  sessions will pick it up.
- Suggest running `/nachhilfe-vocab` or `/nachhilfe-status` next.
