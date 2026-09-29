# Privacy

NachhilfeBot runs entirely on your machine. The author does not collect,
receive, or store any of your data.

## What the plugin stores

Your profile, vocabulary cards, session log (date, time, type, minutes,
score, topic, mistake tags) and settings are written as JSON files to a
`nachhilfe/` folder inside the directory you start Claude Code from. Nothing
is written anywhere else. Writing and reading sessions keep only the topic,
score and minutes, not the text you submitted.

Delete the `nachhilfe/` folder to delete all of your data. Uninstalling the
plugin never touches it.

## What the plugin runs

- `python3 -m nachhilfe ...`, a small standard-library Python program bundled
  with the plugin, for scheduling, scoring and progress tracking.
- `git rev-parse`, once during `/nachhilfe-init`, to warn you if your data
  folder is inside a git repository.
- A session-start hook that runs `python3 -m nachhilfe session-start-banner`
  to print your streak and how many vocabulary cards are due.

The plugin makes no network requests, has no telemetry or analytics, and
sends nothing to the author or to any third party.

## What Claude sees

The lessons themselves are conversations with Claude inside Claude Code.
Whatever you type in a session, and the plugin's command output, is handled
by Claude Code under Anthropic's own terms and privacy policy, exactly like
any other Claude Code conversation:
<https://www.anthropic.com/legal/privacy>

## Contact

Questions or concerns: open an issue at
<https://github.com/doszhan/nachhilfebot/issues> or visit
<https://devoption.de>.
