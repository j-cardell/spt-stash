#!/usr/bin/env python3
"""SPT Stash — background QThread workers for mod install, download, fika sync."""

import logging
import re
import shutil
import subprocess
import time
import urllib.error
import zipfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .. import paths
from ..catalog.dependencies import fetch_mod_dependencies_sync
from ..catalog.http import urlopen_with_certs
from ..catalog.matching import find_best_catalog_match_global
from ..paths import DOWNLOADS_CACHE_DIR
from .links import create_relative_symlink
from .metadata import load_mod_meta, save_mod_meta

logger = logging.getLogger(__name__)


def normalize_windows_paths(root):
    """Turn entries literally named 'BepInEx\\plugins\\X.dll' (zips built on Windows) into real folders.

    Returns the number of files fixed. Empty directory markers ('A\\B\\') are dropped.
    """
    fixed = 0
    for p in [q for q in Path(root).rglob("*") if "\\" in q.name]:
        if p.name.endswith("\\"):  # directory marker the extractor wrote as a 0-byte file
            if p.is_file() and p.stat().st_size == 0:
                p.unlink()
            continue
        dest = p.parent / p.name.replace("\\", "/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(dest))
        fixed += 1
    return fixed


# Archive folders (relative to the game root) whose files belong in the game folder, not in the mod stash.
GAME_ROOT_DIRS = ("EscapeFromTarkov_Data", "BepInEx/patchers")


def install_game_root_files(extract_dir, game_root):
    """Copy files an archive ships for the game folder (e.g. EscapeFromTarkov_Data/Managed/*.dll).

    Dynamic Maps needs Unity.VectorGraphics.dll there. Existing files are never overwritten, and nothing
    outside GAME_ROOT_DIRS is touched. shortcut: these files aren't tracked per mod, so deleting a mod leaves
    them behind, add a manifest in .meta.json if that ever matters.
    Returns the relative paths added.
    """
    extract_dir, game_root = Path(extract_dir).resolve(), Path(game_root).resolve()
    added = []
    for sub in GAME_ROOT_DIRS:
        src_root = extract_dir / sub
        if not src_root.is_dir():
            continue
        for src in sorted(p for p in src_root.rglob("*") if p.is_file()):
            rel = src.relative_to(extract_dir)
            dest = (game_root / rel).resolve()
            if game_root not in dest.parents or dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            added.append(rel.as_posix())
    return added


class ModInstallerThread(QThread):
    finished = Signal(bool, str)

    def __init__(self, archive_path, mod_info=None, excluded_files=None):
        super().__init__()
        self.archive_path = Path(archive_path)
        self.mod_info = mod_info
        self.excluded_files = set(excluded_files) if excluded_files else set()

    def _save_staged_metadata(self, target_staged):
        if not target_staged.is_dir():
            return
        meta = self.mod_info
        if not meta:
            matched = find_best_catalog_match_global(target_staged.name) or find_best_catalog_match_global(
                self.archive_path.name
            )
            if matched:
                meta = {
                    "name": target_staged.name,
                    "title": matched.get("title", target_staged.name),
                    "link": matched.get("link", ""),
                    "author": matched.get("creator", "Community"),
                    "version": matched.get("version", "1.0.0"),
                    "image_url": matched.get("image_url", ""),
                    "category": matched.get("category", "Other"),
                    "description": matched.get("description", ""),
                    "source": "local_archive_matched",
                }
            else:
                clean_disp = re.sub(r"([a-z])([A-Z])", r"\1 \2", re.sub(r"\.dll$", "", target_staged.name, flags=re.I))
                meta = {
                    "name": target_staged.name,
                    "title": clean_disp,
                    "link": "",
                    "author": "Local Archive",
                    "version": "1.0.0",
                    "image_url": "",
                    "category": "Custom Local Mod",
                    "description": f"Locally installed archive package ({self.archive_path.name})",
                    "source": "local_archive_unlisted",
                }
        save_mod_meta(target_staged, meta)

    def run(self):
        try:
            temp_extract = DOWNLOADS_CACHE_DIR / f"temp_{self.archive_path.stem}"
            if temp_extract.exists():
                shutil.rmtree(temp_extract)
            temp_extract.mkdir(parents=True, exist_ok=True)

            if self.archive_path.suffix.lower() == ".zip":
                with zipfile.ZipFile(self.archive_path, "r") as z:
                    z.extractall(temp_extract)
            elif self.archive_path.suffix.lower() == ".7z":
                res = subprocess.run(
                    ["7z", "x", "-y", f"-o{temp_extract}", str(self.archive_path)],
                    capture_output=True,
                    text=True,
                )
                if res.returncode != 0:
                    self.finished.emit(False, f"7z Extraction error: {res.stderr}")
                    return
            else:
                self.finished.emit(False, "Unsupported archive format.")
                return

            normalize_windows_paths(temp_extract)

            # Purge user-excluded files
            if self.excluded_files:
                for p in list(temp_extract.rglob("*")):
                    if p.is_file():
                        rel_str = str(p.relative_to(temp_extract)).replace("\\", "/")
                        filename = p.name
                        if (
                            rel_str in self.excluded_files
                            or filename in self.excluded_files
                            or any(ex in rel_str for ex in self.excluded_files)
                        ):
                            try:
                                p.unlink()
                            except Exception:
                                pass

            bepin_src = None
            user_mods_src = None

            for p in temp_extract.rglob("*"):
                if p.is_dir():
                    if p.name.lower() == "plugins" and p.parent.name.lower() == "bepinex":
                        bepin_src = p
                    elif p.name.lower() == "mods" and p.parent.name.lower() == "user":
                        user_mods_src = p

            if bepin_src:
                self._stage_items(bepin_src, paths.STAGED_CLIENT, paths.CLIENT_MODS_DIR, from_bepin=True)
            if user_mods_src:
                self._stage_items(user_mods_src, paths.STAGED_SERVER, paths.SERVER_MODS_DIR, temp_extract=temp_extract)

            install_game_root_files(temp_extract, paths.CLIENT_MODS_DIR.parent.parent)

            if not bepin_src and not user_mods_src:
                top_items = [p for p in temp_extract.iterdir() if not p.name.startswith(".")]
                for item in top_items:
                    is_server = (item / "package.json").exists() if item.is_dir() else False
                    target_staged_dir = paths.STAGED_SERVER if is_server else paths.STAGED_CLIENT
                    target_live_dir = paths.SERVER_MODS_DIR if is_server else paths.CLIENT_MODS_DIR

                    target_staged = target_staged_dir / item.name
                    if target_staged.exists():
                        if target_staged.is_dir():
                            shutil.rmtree(target_staged)
                        else:
                            target_staged.unlink()
                    shutil.move(str(item), str(target_staged))

                    create_relative_symlink(target_staged, target_live_dir / item.name)
                    self._save_staged_metadata(target_staged)

            if temp_extract.exists():
                shutil.rmtree(temp_extract)

            if DOWNLOADS_CACHE_DIR in self.archive_path.parents and self.archive_path.exists():
                try:
                    self.archive_path.unlink()
                except Exception:
                    pass

            self.finished.emit(True, f"Successfully staged && symlinked {self.archive_path.name}")
        except Exception as e:
            self.finished.emit(False, str(e))

    def _stage_items(self, src_dir, staged_dir, live_dir, from_bepin=False, temp_extract=None):
        """Shared per-item stage+link loop used by both the client and server branches."""
        for item in src_dir.iterdir():
            # SVM: Greed.exe sits at the archive root and must be copied into the SVM mod dir
            if temp_extract is not None:
                greed_root = temp_extract / "Greed.exe"
                if greed_root.exists() and item.is_dir() and "server value modifier" in item.name.lower():
                    try:
                        shutil.copy2(greed_root, item / "Greed.exe")
                    except Exception as e:
                        logger.warning("Failed to copy Greed.exe into %s: %s", item.name, e)

            target_staged = staged_dir / item.name
            bak_path = target_staged.parent / f".{target_staged.name}.bak"

            if bak_path.exists():
                if bak_path.is_dir():
                    shutil.rmtree(bak_path)
                else:
                    bak_path.unlink()

            if target_staged.exists():
                target_staged.rename(bak_path)

            try:
                shutil.move(str(item), str(target_staged))
                if bak_path.exists():
                    if bak_path.is_dir():
                        shutil.rmtree(bak_path)
                    else:
                        bak_path.unlink()
            except Exception as swap_err:
                if bak_path.exists():
                    if target_staged.exists():
                        if target_staged.is_dir():
                            shutil.rmtree(target_staged)
                        else:
                            target_staged.unlink()
                    bak_path.rename(target_staged)
                raise swap_err

            create_relative_symlink(target_staged, live_dir / item.name)
            self._save_staged_metadata(target_staged)


class FikaSyncThread(QThread):
    updated = Signal(str, str)

    def __init__(self, mods_to_check, parent=None):
        super().__init__(parent)
        self.mods_to_check = mods_to_check

    def run(self):
        for mod in self.mods_to_check:
            name = mod.get("name")
            if not name:
                continue
            staged_p = mod.get("staged_path")
            matched = find_best_catalog_match_global(name)
            if matched and matched.get("link"):
                try:
                    fetch_mod_dependencies_sync(matched)
                    f_stat = matched.get("fika_status")
                    if f_stat and f_stat != "Unknown":
                        meta = load_mod_meta(staged_p) or {}
                        meta["fika_status"] = f_stat
                        if mod.get("client_staged"):
                            save_mod_meta(mod["client_staged"], meta)
                        if mod.get("server_staged"):
                            save_mod_meta(mod["server_staged"], meta)
                        self.updated.emit(name, f_stat)
                except Exception as e:
                    logger.warning("Failed to persist fika status for %s: %s", name, e)


class ModDownloaderThread(QThread):
    progress = Signal(int, str)
    finished = Signal(bool, str, Path)

    def __init__(self, download_url, mod_title, parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.mod_title = mod_title

    def run(self):
        try:
            self.progress.emit(10, "Connecting to download server...")
            res = None
            for attempt in range(4):
                try:
                    res = urlopen_with_certs(self.download_url, timeout=15)
                    break
                except urllib.error.HTTPError as e:
                    if e.code not in (429, 503) or attempt == 3:
                        raise
                    # sp-mod.com rate-limits bursts (preset/dependency queues): honour Retry-After, else back off.
                    retry_after = e.headers.get("Retry-After", "")
                    wait = int(retry_after) if retry_after.isdigit() else 3 * 2**attempt
                    self.progress.emit(10, f"Rate limited by sp-mod.com, retrying in {wait}s...")
                    time.sleep(min(wait, 60))

            disposition = res.headers.get("Content-Disposition", "")
            filename = None
            if "filename=" in disposition:
                filename = disposition.split("filename=")[-1].strip('"; ')

            if not filename:
                final_url = res.url
                filename = Path(final_url.split("?")[0]).name
                if not filename or filename == "download":
                    filename = f"{self.mod_title.replace(' ', '_')}.zip"

            filename = Path(filename).name or f"{self.mod_title.replace(' ', '_')}.zip"  # strip any path components
            target_file = DOWNLOADS_CACHE_DIR / filename

            content_length = res.headers.get("Content-Length")
            total_bytes = int(content_length) if content_length and content_length.isdigit() else 0

            downloaded = 0
            block_size = 65536
            with open(target_file, "wb") as f:
                while True:
                    buffer = res.read(block_size)
                    if not buffer:
                        break
                    f.write(buffer)
                    downloaded += len(buffer)
                    if total_bytes > 0:
                        percent = int((downloaded / total_bytes) * 100)
                        self.progress.emit(
                            percent,
                            f"Downloading... {downloaded // 1024} KB / {total_bytes // 1024} KB ({percent}%)",
                        )
                    else:
                        self.progress.emit(50, f"Downloading... {downloaded // 1024} KB downloaded")

            self.progress.emit(100, f"Download Complete ({filename})")
            self.finished.emit(True, f"Successfully downloaded {filename}", target_file)
        except Exception as e:
            self.finished.emit(False, str(e), Path(""))
