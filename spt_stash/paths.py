#!/usr/bin/env python3
"""
SPT Stash — Centralized path discovery and directory management.

Single source of truth for every filesystem location SPT Stash touches.
`ensure_dirs()` performs all mkdir() calls explicitly (called once from
spt_stash.main() at startup), so importing this module has zero side effects.
"""

import json
import os
from pathlib import Path

# ── Application data dirs ────────────────────────────────────────────────────
CONFIG_DIR = Path.home() / ".config" / "spt-mod-manager"
CONFIG_FILE = CONFIG_DIR / "config.json"
PRESETS_DIR = CONFIG_DIR / "presets"

CACHE_DIR = Path.home() / ".cache" / "spt-mod-manager"
CATALOG_CACHE_FILE = CACHE_DIR / "catalog.json"
IMAGE_CACHE_DIR = CACHE_DIR / "images"
DOWNLOADS_CACHE_DIR = CACHE_DIR / "downloads"


def _default_spt_root() -> Path:
    return (Path.home() / "Games" / "SPT").resolve()


# Staging root defaults to <SPT_ROOT>/.staged; STAGED_* are derived from it.
# These module-level defaults are used by code paths that haven't yet been
# migrated to take an explicit AppConfig. They are overwritten at startup.
STAGED_DIR = (_default_spt_root() / ".staged").resolve()
STAGED_CLIENT = STAGED_DIR / "client"
STAGED_SERVER = STAGED_DIR / "server"

SP_MOD_RSS_URL = "https://sp-mod.com/mods/rss"


def client_mods_dir(spt_root: Path) -> Path:
    return Path(spt_root) / "BepInEx" / "plugins"


def server_mods_dir(spt_root: Path) -> Path:
    return Path(spt_root) / "SPT_Runtime" / "user" / "mods"


def find_spt_root() -> Path:
    """Locate the SPT installation root: env var → config file → common paths."""
    if "SPT_PATH" in os.environ and Path(os.environ["SPT_PATH"]).exists():
        return Path(os.environ["SPT_PATH"]).resolve()

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
                if "spt_path" in cfg and Path(cfg["spt_path"]).exists():
                    return Path(cfg["spt_path"]).resolve()
        except Exception:
            pass

    try:
        script_dir = Path(__file__).parent.resolve()
        if str(script_dir).startswith("/tmp/.mount_"):
            script_dir = None
    except Exception:
        script_dir = None

    # Prioritize standard SPT installation directories FIRST
    candidates = [
        Path.home() / "Games" / "SPT",
        Path.home() / "Games" / "SinglePlayerTarkov",
        Path.home() / ".games" / "SPT",
        Path.home() / "spt",
    ]
    if script_dir:
        candidates.append(script_dir)
    candidates.append(Path.cwd().resolve())

    for cand in candidates:
        if cand.exists() and (
            (cand / "SPT_Runtime").exists() or (cand / "BepInEx").exists() or (cand / "launcher.sh").exists()
        ):
            return cand.resolve()

    return Path.home() / "Games" / "SPT"


def apply_spt_root(spt_root: Path) -> None:
    """Point the module-level STAGED_* constants at a new SPT root at startup."""
    global STAGED_DIR, STAGED_CLIENT, STAGED_SERVER, CLIENT_MODS_DIR, SERVER_MODS_DIR
    root = Path(spt_root).resolve()
    STAGED_DIR = (root / ".staged").resolve()
    STAGED_CLIENT = STAGED_DIR / "client"
    STAGED_SERVER = STAGED_DIR / "server"
    CLIENT_MODS_DIR = client_mods_dir(root)
    SERVER_MODS_DIR = server_mods_dir(root)


# Back-compat: set on first import so legacy callers keep working until main() runs.
_default_root = _default_spt_root()
CLIENT_MODS_DIR = client_mods_dir(_default_root)
SERVER_MODS_DIR = server_mods_dir(_default_root)


def ensure_dirs() -> None:
    """Create every app directory. Called once from main() at startup — never at import."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    STAGED_CLIENT.mkdir(parents=True, exist_ok=True)
    STAGED_SERVER.mkdir(parents=True, exist_ok=True)
