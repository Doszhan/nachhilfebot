"""Local database helpers for <cwd>/nachhilfe/<lang>/*.json.

Skills call the `nachhilfe` CLI (cli.py) and never read/write these files
directly, so every skill only ever sees the slice of data it asked for and
aggregation logic stays in one place.

The data root is always `<cwd>/nachhilfe`, resolved fresh from the current
working directory on every invocation — there is no global pointer file.
Each working directory has its own independent data: running `/nachhilfe-*`
commands from a different folder means different (or missing) data, by
design. If no `nachhilfe/` folder exists in the current directory,
`get_data_root()` raises, telling the caller to either `cd` to their usual
working folder or run `/nachhilfe-init` to create one here.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "templates"

SCHEMA_VERSION = 1

GENERIC_TEMPLATES = ["status", "vocab", "reading", "writing", "mastery-thresholds"]

CUSTOM_PROMPTS_TEMPLATE = (
    "# Custom prompts for this learner\n\n"
    "<!-- Add standing preferences here, one bullet each, e.g.: -->\n"
    "<!-- - Always use informal \"du\" register in writing tasks. -->\n"
    "<!-- - Prefer topics related to travel and food. -->\n\n"
    "<!-- Every /nachhilfe-* skill reads this file before generating a task. -->\n"
    "<!-- Only add something here when you explicitly ask for it to be remembered; -->\n"
    "<!-- one-off customizations passed inline to a command are not saved here. -->\n"
)


def _resolve_data_root() -> Path | None:
    data_dir = Path.cwd() / "nachhilfe"
    return data_dir if data_dir.exists() else None


def get_data_root() -> Path:
    """Resolve `<cwd>/nachhilfe`, raising if it doesn't exist here."""
    data_dir = _resolve_data_root()
    if data_dir is None:
        raise SystemExit(
            "No nachhilfe/ directory found in the current folder.\n"
            "cd to the folder where you usually run nachhilfe commands, "
            "or run /nachhilfe-init here to create a new one."
        )
    return data_dir


def set_data_root(base_dir: Path) -> Path:
    """Ensure `<base_dir>/nachhilfe` exists and return it.

    Every working directory has its own independent data root — nothing is
    persisted outside `<base_dir>/nachhilfe` itself.
    """
    data_dir = base_dir.expanduser().resolve() / "nachhilfe"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def config_path() -> Path:
    return get_data_root() / "config.json"


def load_config() -> dict:
    data_dir = _resolve_data_root()
    if data_dir is None:
        return {}
    path = data_dir / "config.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_config(config: dict) -> None:
    get_data_root().mkdir(parents=True, exist_ok=True)
    config_path().write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def active_language() -> str:
    config = load_config()
    lang = config.get("active_language")
    if not lang:
        raise SystemExit("No active language set. Run /nachhilfe-init first.")
    return lang


def lang_dir(lang: str | None = None) -> Path:
    return get_data_root() / (lang or active_language())


def db_path(name: str, lang: str | None = None) -> Path:
    return lang_dir(lang) / f"{name}.json"


def load_db(name: str, lang: str | None = None) -> dict:
    path = db_path(name, lang)
    if not path.exists():
        raise SystemExit(f"{path} not found. Run /nachhilfe-init first.")
    return json.loads(path.read_text())


def save_db(name: str, data: dict, lang: str | None = None) -> None:
    path = db_path(name, lang)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _copy_language_template(subdir: str, lang: str, dest_name: str, dest_dir: Path) -> None:
    src = TEMPLATES_DIR / subdir / f"{lang}.json"
    if not src.exists():
        src = TEMPLATES_DIR / subdir / "default.json"
    dest = dest_dir / f"{dest_name}.json"
    if not dest.exists():
        shutil.copy(src, dest)


def init_language(lang: str) -> Path:
    """Create <data_dir>/<lang>/ from the bundled JSON templates.

    Idempotent: existing files are left untouched so re-running init never
    clobbers a learner's history.
    """
    target = get_data_root() / lang
    target.mkdir(parents=True, exist_ok=True)

    for name in GENERIC_TEMPLATES:
        src = TEMPLATES_DIR / f"{name}.json"
        dest = target / f"{name}.json"
        if not dest.exists():
            shutil.copy(src, dest)

    _copy_language_template("level-hours", lang, "level-hours", target)
    _copy_language_template("grammar", lang, "grammar", target)

    prompts_file = target / "CUSTOM_PROMPTS.md"
    if not prompts_file.exists():
        prompts_file.write_text(CUSTOM_PROMPTS_TEMPLATE)

    return target
