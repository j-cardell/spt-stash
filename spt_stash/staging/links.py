#!/usr/bin/env python3
"""SPT Stash — symlink stage/purge helpers."""

import os
import shutil
from pathlib import Path

from .. import paths


def remove_path(p):
    """Remove a file, symlink, or directory tree at p, if it exists."""
    p = Path(p)
    if not (p.is_symlink() or p.exists()):
        return
    if p.is_symlink() or not p.is_dir():
        p.unlink()
    else:
        shutil.rmtree(p)


def create_relative_symlink(src_staged, dst_live):
    """Create dst_live → src_staged as a relative in-tree symlink (abs fallback)."""
    src = Path(src_staged).resolve()
    dst = Path(dst_live)
    dst.parent.mkdir(parents=True, exist_ok=True)
    remove_path(dst)

    try:
        rel_target = os.path.relpath(src, dst.parent)
        os.symlink(rel_target, dst)
    except Exception:
        os.symlink(str(src), str(dst))


def _purge_single(staged_item, live_link):
    """Remove live link + staged dir + sidecar, shared by both branches."""
    remove_path(live_link)
    if staged_item.exists():
        if staged_item.is_dir():
            shutil.rmtree(staged_item)
        else:
            staged_item.unlink()
    meta_p = staged_item.parent / f".{staged_item.name}.meta.json"
    if meta_p.exists():
        meta_p.unlink()


def purge_mod_files_and_symlinks(mod_data):
    if not mod_data:
        return

    if isinstance(mod_data, dict):
        for item, live_link, _ in mod_data.get("client_items", []):
            _purge_single(item, live_link)
        for item, live_link, _ in mod_data.get("server_items", []):
            _purge_single(item, live_link)
    else:
        mod_name = str(mod_data)
        for base_staged, base_live in [
            (paths.STAGED_CLIENT, paths.CLIENT_MODS_DIR),
            (paths.STAGED_SERVER, paths.SERVER_MODS_DIR),
        ]:
            _purge_single(base_staged / mod_name, base_live / mod_name)


# SPT's own client plugins live in BepInEx/plugins/spt — never adopt (disabling it breaks the game).
_PROTECTED_LIVE = {"spt"}


def adopt_unmanaged_mods(staged_dir, live_dir):
    """Move manually installed mods (real files/dirs in live_dir) into staged_dir and symlink them back.

    Makes hand-installed mods show up in the Installed tab. Returns the number adopted.
    """
    staged_dir, live_dir = Path(staged_dir), Path(live_dir)
    if not live_dir.is_dir():
        return 0
    staged_dir.mkdir(parents=True, exist_ok=True)
    adopted = 0
    for item in live_dir.iterdir():
        if item.is_symlink() or item.name.startswith(".") or item.name.lower() in _PROTECTED_LIVE:
            continue
        target = staged_dir / item.name
        if target.exists():
            continue  # name clash: leave the live copy alone rather than overwrite either side
        try:
            shutil.move(str(item), str(target))
            create_relative_symlink(target, item)
            adopted += 1
        except OSError as e:
            print(f"Could not adopt {item}: {e}")
    return adopted
