#!/usr/bin/env python3
"""SPT Stash — symlink stage/purge helpers."""

import os
import shutil
from pathlib import Path

from .. import paths


def create_relative_symlink(src_staged, dst_live):
    """Create dst_live → src_staged as a relative in-tree symlink (abs fallback)."""
    src = Path(src_staged).resolve()
    dst = Path(dst_live)
    if dst.is_symlink() or dst.exists():
        if dst.is_symlink() or not dst.is_dir():
            dst.unlink()
        else:
            shutil.rmtree(dst)

    try:
        rel_target = os.path.relpath(src, dst.parent)
        os.symlink(rel_target, dst)
    except Exception:
        os.symlink(str(src), str(dst))


def _purge_single(staged_item, live_link):
    """Remove live link + staged dir + sidecar, shared by both branches."""
    if live_link.is_symlink() or live_link.exists():
        if live_link.is_symlink() or not live_link.is_dir():
            live_link.unlink()
        else:
            shutil.rmtree(live_link)
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
