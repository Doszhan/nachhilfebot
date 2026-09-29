---
name: nachhilfe-config
description: View or change nachhilfebot settings for the active language — hours needed per CEFR level transition, or the FSRS stability thresholds that classify vocab as "very good"/"good"/"in learning". Use only when invoked as /nachhilfe-config.
disable-model-invocation: true
---

# nachhilfebot: config

Figure out what the learner wants to see or change, then use the relevant
command. Always print the resulting file back to them after any change so
they can confirm it took effect.

## View current settings

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe config-get --file level-hours
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe config-get --file mastery-thresholds
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe config-get --file profile
```

## Change hours needed for a level transition

Transition keys look like `"B1->B2"` (use `"0->A1"` for absolute-beginner
to A1).

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe config-set-hours --transition "B1->B2" --hours <number>
```

## Change an FSRS mastery threshold

`very_good_stability_days` and `good_stability_days` are the FSRS-stability
cutoffs (in days) used by `/nachhilfe-status`'s vocabulary mastery
breakdown.

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe config-set-threshold --key very_good_stability_days --value <number>
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe config-set-threshold --key good_stability_days --value <number>
```

`good_stability_days` should stay below `very_good_stability_days` — warn
the learner if a change would invert them, but let them proceed if they
insist.

## Editing the grammar topic taxonomy

There's no dedicated command for this — the taxonomy lives in
`grammar.json`'s `topics` field in the language's data directory
(`python3 -m nachhilfe paths` gives you the path) and is safe to hand-edit
directly, since it's a small config list rather than growing session data.
If the learner wants topics added/renamed, edit that file's `topics`
object for the relevant level directly.
