#!/usr/bin/env python3
"""SPT Stash — load/save JSON config and the canonical AppConfig bundle."""

import json
from dataclasses import dataclass
from pathlib import Path

from .paths import CONFIG_FILE, find_spt_root


def load_config():
    """Load config.json over sane defaults. Never raises."""
    spt_root = find_spt_root()
    defaults = {
        "spt_path": str(spt_root),
        "staged_dir": str(spt_root / ".staged"),
        "server_script": str(spt_root / "server.sh"),
        "launcher_script": str(spt_root / "launcher.sh"),
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
                defaults.update(cfg)
        except Exception:
            pass
    return defaults


def save_config(cfg_dict):
    """Persist config.json. Errors are printed, never raised."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg_dict, f, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}")


@dataclass
class AppConfig:
    """Resolved, canonical app paths — computed once in main(), never re-read."""

    spt_root: Path
    staged_dir: Path
    staged_client: Path
    staged_server: Path
    server_script: Path
    launcher_script: Path

    @property
    def client_mods_dir(self) -> Path:
        return self.spt_root / "BepInEx" / "plugins"

    @property
    def server_mods_dir(self) -> Path:
        return self.spt_root / "SPT_Runtime" / "user" / "mods"

    @classmethod
    def from_disk(cls) -> "AppConfig":
        cfg = load_config()
        spt_root = Path(cfg["spt_path"]).resolve()
        staged_dir = Path(cfg.get("staged_dir", spt_root / ".staged")).resolve()
        return cls(
            spt_root=spt_root,
            staged_dir=staged_dir,
            staged_client=staged_dir / "client",
            staged_server=staged_dir / "server",
            server_script=Path(cfg.get("server_script", spt_root / "server.sh")),
            launcher_script=Path(cfg.get("launcher_script", spt_root / "launcher.sh")),
        )
