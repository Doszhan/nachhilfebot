"""Deterministic backend for the nachhilfebot Claude Code plugin.

Skills invoke this package only through `python3 -m nachhilfe <command>`
(see cli.py). Skills never read or write the JSON databases directly, so
aggregation logic stays in one place and stays correct as a learner's
history grows.
"""
