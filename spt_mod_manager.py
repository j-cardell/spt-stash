#!/usr/bin/env python3
"""
SPT Stash — Native Linux Mod Manager for Single Player Tarkov (SPT)
- Manages Installed Client (BepInEx) and Server (user/mods) Mods via Symlink Staging
- Installs local .zip/.7z mod archives with automatic path/separator normalization
- Browses live mod listings from sp-mod.com (The Forge)
- Controls SPT Server & Launcher execution dynamically
"""

import sys
import os
import time
import shutil
import glob
import zipfile
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import webbrowser
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTabWidget, QListWidget, QListWidgetItem, QPushButton, QLabel,
    QLineEdit, QTextBrowser, QSplitter, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QComboBox, QGroupBox, QHeaderView,
    QFrame, QProgressBar, QDialog, QTreeWidget, QTreeWidgetItem, QCheckBox,
    QStyledItemDelegate, QStyle, QAbstractItemView, QMenu, QScrollArea
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl, QSize
from PySide6.QtGui import QFont, QColor, QIcon, QDesktopServices, QPixmap, QImage, QTextDocument, QPainter, QBrush, QPen
import json
import re
import html

CACHE_DIR = Path.home() / ".cache" / "spt-mod-manager"
CATALOG_CACHE_FILE = CACHE_DIR / "catalog.json"
IMAGE_CACHE_DIR = CACHE_DIR / "images"
DOWNLOADS_CACHE_DIR = CACHE_DIR / "downloads"

STAGED_DIR = Path.home() / ".local" / "share" / "spt-mod-manager" / "staged"
STAGED_CLIENT = STAGED_DIR / "client"
STAGED_SERVER = STAGED_DIR / "server"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
STAGED_CLIENT.mkdir(parents=True, exist_ok=True)
STAGED_SERVER.mkdir(parents=True, exist_ok=True)


def detect_installed_spt_version():
    spt_root = SPT_ROOT.resolve() if 'SPT_ROOT' in globals() else Path.home() / "Games" / "SPT"
    dll_path = spt_root / "SPT_Runtime" / "SPTarkov.Server.Core.dll"
    if dll_path.exists():
        try:
            res = subprocess.run(['strings', str(dll_path)], capture_output=True, text=True)
            matches = re.findall(r'\b(4\.\d+\.\d+)\b', res.stdout)
            if matches:
                return f"SPT {matches[0]}"
        except Exception:
            pass
    return "SPT 4.1.3"


def check_dep_status(dep_title):
    spt_root = SPT_ROOT.resolve() if 'SPT_ROOT' in globals() else Path.home() / "Games" / "SPT"
    staged_dir = STAGED_DIR.resolve() if 'STAGED_DIR' in globals() else Path.home() / ".local" / "share" / "spt-mod-manager" / "staged"

    clean_title = re.sub(r'\.dll$', '', dep_title, flags=re.I)
    ignore_words = {'mod', 'mods', 'the', 'and', 'for', 'with', 'spt', 'tarkov', 'expanded', 'navmesh', 'dll', 'exe', 'plugin', 'plugins'}
    words = [w.lower() for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', clean_title) if w.lower() not in ignore_words]
    if not words:
        words = [clean_title.lower().strip()]

    # 1. Check if ENABLED in active game dirs
    game_dirs = [spt_root / "BepInEx" / "plugins", spt_root / "SPT_Runtime" / "user" / "mods"]
    for d in game_dirs:
        if d.exists():
            for p in d.iterdir():
                if any(w in p.name.lower() for w in words):
                    return "ENABLED", p

    # 2. Check if STAGED in stash (disabled)
    staged_dirs = [staged_dir / "client", staged_dir / "server"]
    for d in staged_dirs:
        if d.exists():
            for p in d.iterdir():
                if any(w in p.name.lower() for w in words):
                    return "STAGED_DISABLED", p

    return "MISSING", None


def parse_version_tuple(ver_str):
    if not ver_str:
        return (0, 0, 0)
    clean = re.sub(r'^[vV]', '', str(ver_str).strip())
    parts = re.findall(r'\d+', clean)
    return tuple(int(p) for p in parts[:4]) if parts else (0, 0, 0)


def is_version_newer(latest_ver, current_ver):
    return parse_version_tuple(latest_ver) > parse_version_tuple(current_ver)


def resolve_author_profile_url(mod_dict):
    staged_p = mod_dict.get("staged_path")
    meta = load_mod_meta(staged_p) or {} if staged_p else {}
    if meta.get("author_link"):
        return meta.get("author_link")

    matched = find_best_catalog_match_global(mod_dict["name"])
    mod_url = meta.get("link") or (matched.get("link") if matched else None)
    
    if mod_url:
        try:
            req = urllib.request.Request(mod_url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
            raw_html = urllib.request.urlopen(req, timeout=6).read().decode("utf-8")
            user_links = re.findall(r'href=[\'\"](https?://sp-mod\.com/user/\d+/[^\'\"]+|/user/\d+/[^\'\"]+)[\'\"]', raw_html)
            if user_links:
                profile_url = user_links[0]
                if profile_url.startswith("/"):
                    profile_url = f"https://sp-mod.com{profile_url}"
                
                meta["author_link"] = profile_url
                if mod_dict.get("client_staged"): save_mod_meta(mod_dict["client_staged"], meta)
                if mod_dict.get("server_staged"): save_mod_meta(mod_dict["server_staged"], meta)
                return profile_url
        except Exception:
            pass

    author_str = meta.get("author") or (matched.get("creator") if matched else "Community")
    return f"https://sp-mod.com/mods?query={urllib.parse.quote(author_str)}"


def is_dependency_installed(dep_title):
    status, _ = check_dep_status(dep_title)
    return status == "ENABLED"


def purge_mod_files_and_symlinks(mod_data):
    if not mod_data:
        return

    if isinstance(mod_data, dict):
        client_items = mod_data.get("client_items", [])
        server_items = mod_data.get("server_items", [])
        for item, live_link, _ in client_items:
            if live_link.is_symlink() or live_link.exists():
                if live_link.is_symlink() or not live_link.is_dir(): live_link.unlink()
                else: shutil.rmtree(live_link)
            if item.exists():
                if item.is_dir(): shutil.rmtree(item)
                else: item.unlink()
            meta_p = item.parent / f".{item.name}.meta.json"
            if meta_p.exists(): meta_p.unlink()

        for item, live_link, _ in server_items:
            if live_link.is_symlink() or live_link.exists():
                if live_link.is_symlink() or not live_link.is_dir(): live_link.unlink()
                else: shutil.rmtree(live_link)
            if item.exists():
                if item.is_dir(): shutil.rmtree(item)
                else: item.unlink()
            meta_p = item.parent / f".{item.name}.meta.json"
            if meta_p.exists(): meta_p.unlink()
    else:
        mod_name = str(mod_data)
        for base_staged, base_live in [(STAGED_CLIENT, CLIENT_MODS_DIR), (STAGED_SERVER, SERVER_MODS_DIR)]:
            staged = base_staged / mod_name
            live = base_live / mod_name
            if live.is_symlink() or live.exists():
                if live.is_symlink() or not live.is_dir(): live.unlink()
                else: shutil.rmtree(live)
            if staged.exists():
                if staged.is_dir(): shutil.rmtree(staged)
                else: staged.unlink()
            meta_p = base_staged / f".{mod_name}.meta.json"
            if meta_p.exists(): meta_p.unlink()


def fetch_mod_dependencies_sync(mod_info):
    deps = []
    seen = set()
    url = mod_info.get("link") if isinstance(mod_info, dict) else str(mod_info)
    if not url:
        return deps

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
        raw_html = urllib.request.urlopen(req, timeout=6).read().decode("utf-8")

        if isinstance(mod_info, dict):
            m_guid = re.search(r'GUID</h3>[\s\S]{1,200}?<span[^>]*font-mono[^>]*>\s*([^\s<]+)', raw_html, re.I)
            if m_guid: mod_info["guid"] = m_guid.group(1).strip()

            m_lic = re.search(r'License</h3>[\s\S]{1,200}?<a[^>]*>\s*([^<\n]+)', raw_html, re.I)
            if m_lic: mod_info["license"] = html.unescape(m_lic.group(1).strip())

            m_src = re.search(r'Source Code</h3>[\s\S]{1,300}?<a[^>]+href=["\']([^"\']+)["\']', raw_html, re.I)
            if m_src: mod_info["source_code"] = m_src.group(1).strip()

            m_vt = re.search(r'VirusTotal[^<]*</h3>[\s\S]{1,300}?<a[^>]+href=["\']([^"\']+)["\']', raw_html, re.I)
            if m_vt: mod_info["virustotal"] = m_vt.group(1).strip()

            m_fika = re.search(r'(Fika\s+(?:Compatible[^\n<]*|Incompatible|Compatibility[^\n<]*))', raw_html, re.I)
            if m_fika: mod_info["fika_status"] = m_fika.group(1).strip()

            mod_info["has_ai"] = bool(re.search(r'Includes AI Generated Content', raw_html, re.I))

        for m in re.finditer(r'<a[^>]+href=[\"\'](https://sp-mod\.com/mod/\d+/[^\'\"]+)[\"\'][^>]*>(.*?)</a>', raw_html, re.DOTALL):
            link = m.group(1)
            inner = m.group(2)
            if link not in seen and link != url:
                title_m = re.search(r'class=[\"\'][^\"\']*truncate[^\"\']*[\"\'][^>]*>\s*(.*?)\s*</p>', inner, re.DOTALL) or re.search(r'alt=[\"\']([^\"\']+)[\"\']', inner)
                if title_m:
                    clean_title = html.unescape(title_m.group(1).strip())
                    seen.add(link)
                    status, path = check_dep_status(clean_title)
                    deps.append({
                        "title": clean_title,
                        "link": link,
                        "status": status,
                        "path": path,
                        "installed": (status == "ENABLED")
                    })
    except Exception as e:
        print(f"Sync dep fetch error for {url}: {e}")
    return deps


class DependencyFetcherThread(QThread):
    fetched = Signal(dict, list)

    def __init__(self, mod_info, parent=None):
        super().__init__(parent)
        self.mod_info = mod_info

    def run(self):
        deps = fetch_mod_dependencies_sync(self.mod_info)
        self.fetched.emit(self.mod_info, deps)


class RemoteImageTextBrowser(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self._memory_cache = {}

    def loadResource(self, type_id, name):
        if type_id == QTextDocument.ResourceType.ImageResource:
            url_str = name.toString() if hasattr(name, 'toString') else str(name)
            if url_str in self._memory_cache:
                return self._memory_cache[url_str]

            if url_str.startswith("http://") or url_str.startswith("https://"):
                # Disk cache path
                img_name = Path(url_str).name
                local_path = IMAGE_CACHE_DIR / img_name

                if local_path.exists():
                    img = QImage(str(local_path))
                    if not img.isNull():
                        self._memory_cache[url_str] = img
                        return img

                try:
                    req = urllib.request.Request(url_str, headers={"User-Agent": "Mozilla/5.0"})
                    data = urllib.request.urlopen(req, timeout=5).read()
                    img = QImage()
                    if img.loadFromData(data):
                        img.save(str(local_path))
                        self._memory_cache[url_str] = img
                        return img
                except Exception:
                    pass
        return super().loadResource(type_id, name)


class RSSFetcherThread(QThread):
    fetched = Signal(list)
    progress = Signal(str)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.force_refresh = False

    def run(self):
        try:
            # Check local disk cache first unless force_refresh is requested
            if not self.force_refresh and CATALOG_CACHE_FILE.exists():
                with open(CATALOG_CACHE_FILE, "r", encoding="utf-8") as f:
                    mods = json.load(f)
                self.progress.emit(f"Loaded {len(mods)} mods from offline disk cache (0 network requests made). Click 'Refresh sp-mod.com Feed' to check for online updates.")
                self.fetched.emit(mods)
                return

            mods = []
            seen = set()

            # Page through sp-mod.com catalog
            for page in range(1, 15):
                url = f"https://sp-mod.com/mods?perPage=50&page={page}"
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
                )
                try:
                    raw_html = urllib.request.urlopen(req, timeout=8).read().decode("utf-8")
                except Exception:
                    break

                blocks = raw_html.split('href="https://sp-mod.com/mod/')[1:]
                if not blocks:
                    break

                for b in blocks:
                    m_link = re.search(r'^(\d+/[a-zA-Z0-9\-_]+)', b)
                    if not m_link:
                        continue
                    full_link = f"https://sp-mod.com/mod/{m_link.group(1)}"
                    if full_link in seen:
                        continue
                    seen.add(full_link)

                    # Title
                    m_title = re.search(r'<span class="group-hover:underline">\s*(.*?)\s*</span>', b, re.DOTALL)
                    title = html.unescape(m_title.group(1).strip()) if m_title else m_link.group(1).split('/')[-1].replace('-', ' ').title()

                    # Version
                    m_ver = re.search(r'<span class="text-nowrap font-light text-gray-400">\s*(.*?)\s*</span>', b, re.DOTALL)
                    ver = m_ver.group(1).strip() if m_ver else ''

                    # Creator
                    m_creator = re.search(r'Created by\s+([^<\n]+)', b)
                    creator = m_creator.group(1).strip() if m_creator else 'Community'

                    # Target SPT
                    m_spt = re.search(r'badge-version[^>]*>\s*(SPT[^<\n]+)\s*</p>', b)
                    spt_ver = m_spt.group(1).strip() if m_spt else ''

                    # Description excerpt
                    m_desc = re.search(r'<p class="@lg:block hidden text-gray-300">\s*(.*?)\s*</p>', b, re.DOTALL)
                    desc = html.unescape(m_desc.group(1).strip()) if m_desc else ''

                    # Image Thumbnail
                    m_img = re.search(r'<img[^>]+src=["\'](https://files\.sp-mod\.com/mods/[^\'\"]+)["\']', b)
                    img_url = m_img.group(1) if m_img else ''
                    img_html = f"<div style='margin-bottom:12px;'><img src='{img_url}' style='max-width:240px; border-radius:8px;'/></div>" if img_url else ""

                    # Downloads & Endorsements
                    m_dl = re.search(r'title=["\']([0-9,]+)\s+Downloads["\']', b, re.I)
                    downloads = int(m_dl.group(1).replace(',', '')) if m_dl else 0

                    m_end = re.search(r'title=["\']([0-9,]+)\s+Endorsements["\']', b, re.I)
                    endorsements = int(m_end.group(1).replace(',', '')) if m_end else 0

                    dl_url = f"https://sp-mod.com/mod/download/{m_link.group(1)}/{ver}" if ver else f"https://sp-mod.com/mod/download/{m_link.group(1)}"

                    mods.append({
                        "title": title,
                        "link": full_link,
                        "download_url": dl_url,
                        "creator": creator,
                        "version": ver,
                        "spt_version": spt_ver,
                        "image_url": img_url,
                        "downloads": downloads,
                        "endorsements": endorsements,
                        "category": "Other",
                        "description": f"{img_html}<h2>{title} <span style='font-size:14px; color:#89b4fa;'>v{ver}</span></h2><p><b>Created by:</b> {creator} | <b>Target:</b> {spt_ver}</p><hr/><p>{desc}</p><p><a href='{full_link}'>Click here to open mod download page on sp-mod.com</a></p>",
                        "date": ""
                    })

                self.progress.emit(f"Updating online catalog... ({len(mods)} mods found)")
                if len(blocks) < 50:
                    break

            # Save to disk cache
            with open(CATALOG_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(mods, f, indent=2)

            self.fetched.emit(mods)
        except Exception as e:
            self.error.emit(str(e))

CONFIG_DIR = Path.home() / ".config" / "spt-mod-manager"
CONFIG_FILE = CONFIG_DIR / "config.json"
PRESETS_DIR = CONFIG_DIR / "presets"
CACHE_DIR = Path.home() / ".cache" / "spt-mod-manager"
CATALOG_CACHE_FILE = CACHE_DIR / "catalog.json"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
PRESETS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def detect_cpu_core_allocation():
    threads = os.cpu_count() or 8
    model_name = "Linux CPU"
    try:
        if Path("/proc/cpuinfo").exists():
            with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
                for line in f:
                    if "model name" in line:
                        model_name = line.split(":")[1].strip()
                        break
    except Exception:
        pass

    if threads <= 8:
        s_cores = "0-3"
        c_cores = f"4-{threads-1}" if threads > 4 else "0-3"
    elif threads <= 12:
        s_cores = "0-3"
        c_cores = f"4-{threads-1}"
    elif threads <= 16:
        s_cores = "0-3"
        c_cores = f"4-{threads-1}"
    elif threads <= 24:
        s_cores = "0-5"
        c_cores = f"6-{threads-1}"
    else:
        s_cores = "0-7"
        c_cores = f"8-{threads-1}"

    return {
        "model_name": model_name,
        "threads": threads,
        "server_cores": s_cores,
        "client_cores": c_cores
    }


def detect_gpu_hardware():
    vendor = "UNKNOWN"
    gpu_name = "Unknown Graphics Card"

    vendor_names = {
        "0x1002": ("AMD", "AMD Radeon Graphics"),
        "0x10de": ("NVIDIA", "NVIDIA GeForce GPU"),
        "0x8086": ("INTEL", "Intel Graphics")
    }

    for vendor_file in sorted(glob.glob("/sys/class/drm/card*/device/vendor")):
        try:
            v_id = Path(vendor_file).read_text(encoding="utf-8").strip().lower()
            if v_id in vendor_names:
                v_info = vendor_names[v_id]
                card_dir = Path(vendor_file).parent
                vram_file = card_dir / "mem_info_vram_total"
                t_mb = 0
                if vram_file.exists():
                    t_mb = int(vram_file.read_text(encoding="utf-8").strip()) / 1024 / 1024
                
                # Prioritize discrete GPU over integrated
                if t_mb > 2000 or vendor == "UNKNOWN":
                    vendor, base_name = v_info
                    gpu_name = f"{base_name} ({t_mb/1024:.0f}GB VRAM)" if t_mb > 0 else base_name
        except Exception:
            pass

    return {
        "vendor": vendor,
        "name": gpu_name
    }


def audit_system_dependencies():
    has_gamemode_bin = shutil.which("gamemoded") is not None or shutil.which("gamemoderun") is not None
    has_gamemode_lib = any(Path(p).exists() for p in [
        "/usr/lib/libgamemode.so", "/usr/lib64/libgamemode.so",
        "/usr/lib/x86_64-linux-gnu/libgamemode.so", "/usr/lib32/libgamemode.so",
        "/usr/lib/libgamemode.so.0", "/usr/lib64/libgamemode.so.0",
        "/usr/lib/x86_64-linux-gnu/libgamemode.so.0"
    ])
    return {
        "mangohud": shutil.which("mangohud") is not None or Path("/usr/bin/mangohud").exists(),
        "taskset": shutil.which("taskset") is not None or Path("/usr/bin/taskset").exists(),
        "gamemode": has_gamemode_bin and has_gamemode_lib,
    }


def find_spt_root():
    if "SPT_PATH" in os.environ and Path(os.environ["SPT_PATH"]).exists():
        return Path(os.environ["SPT_PATH"]).resolve()

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
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
        if cand.exists() and ((cand / "SPT_Runtime").exists() or (cand / "BepInEx").exists() or (cand / "launcher.sh").exists()):
            return cand.resolve()

    return Path.home() / "Games" / "SPT"

SPT_ROOT = find_spt_root()
CLIENT_MODS_DIR = SPT_ROOT / "BepInEx" / "plugins"
SERVER_MODS_DIR = SPT_ROOT / "SPT_Runtime" / "user" / "mods"
LAUNCHER_SCRIPT = SPT_ROOT / "launcher.sh"
SERVER_SCRIPT = SPT_ROOT / "server.sh"
SP_MOD_RSS_URL = "https://sp-mod.com/mods/rss"


def find_best_catalog_match_global(name):
    catalog_mods = []
    if CATALOG_CACHE_FILE.exists():
        try:
            with open(CATALOG_CACHE_FILE, "r", encoding="utf-8") as f:
                catalog_mods = json.load(f)
        except Exception:
            catalog_mods = []
    if not catalog_mods:
        return None

    ALIASES = {
        "tyfonuifixes": "ui-fixes",
        "uifixes": "ui-fixes",
        "drakiaxyzquesttracker": "quest-tracker",
        "deminvincibility": "invincibility",
        "handsarenotbusy": "hands-are-not-busy",
        "borkelrnvg": "borkels-realistic-night-vision-goggles",
        "borkelrnvgserver": "borkels-realistic-night-vision-goggles",
        "amandsgraphics": "amandss-graphics",
        "amandssense": "amands-sense",
        "sain": "sain-solarints-ai-modifications",
        "solarintsainservermod": "sain-solarints-ai-modifications",
        "boxesatref": "boxes-at-ref",
        "svm": "server-value-modifier",
        "tarkinladders": "climbable-ladders",
        "tarkinhideoutuirevamp": "tarkin",
        "rairaihiddencaches": "rais-hidden-caches",
        "wttclientcommonlib": "wtt-commonlib",
        "wttservercommonlib": "wtt-commonlib",
        "moxopixelmenuoverhaul": "wtt-menu-overhaul",
        "drakiaxyzwaypoints": "waypoints-expanded-navmesh",
        "lacypvetweaks": "lacys-pve-tweaks",
        "acidphantasmbepinexconfigurationmanager": "acids-scalable-bepinex-panel",
        "bepinexconfigurationmanager": "acids-scalable-bepinex-panel",
        "acidphantasmarmbandsforall": "armbands-for-all",
        "wttcontentbackport": "wtt-content-backport",
        "wttcontentbackportclient": "wtt-content-backport",
        "randomizzatoremorecases": "more-cases-updated"
    }

    name_clean = re.sub(r'[^a-z0-9]', '', name.lower())
    for alias_k, alias_v in ALIASES.items():
        if alias_k in name_clean:
            for m in catalog_mods:
                if alias_v in m.get("link", "").lower() or alias_v in re.sub(r'[^a-z0-9]', '-', m.get("title", "").lower()):
                    return m

    clean_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', re.sub(r'\.dll$', '', name, flags=re.I))
    target = re.sub(r'[^a-z0-9]', '', clean_name.lower())
    target_stripped = re.sub(r'^[a-z0-9]+[\.\-_]', '', clean_name, flags=re.I)
    target_stripped = re.sub(r'[^a-z0-9]', '', target_stripped.lower())

    for m in catalog_mods:
        m_clean = re.sub(r'[^a-z0-9]', '', m["title"].lower())
        m_slug = re.sub(r'[^a-z0-9]', '', m["link"].split("/")[-1].lower())
        if target in (m_clean, m_slug) or target_stripped in (m_clean, m_slug):
            return m

    for m in catalog_mods:
        m_clean = re.sub(r'[^a-z0-9]', '', m["title"].lower())
        m_slug = re.sub(r'[^a-z0-9]', '', m["link"].split("/")[-1].lower())
        if len(target_stripped) >= 4 and (target_stripped in m_clean or m_clean in target_stripped or target_stripped in m_slug):
            return m

    return None


def save_mod_meta(staged_path, meta_dict):
    if not staged_path:
        return
    if staged_path.is_dir():
        meta_file = staged_path / ".meta.json"
    else:
        meta_file = staged_path.parent / f".{staged_path.name}.meta.json"
    try:
        data = {
            "name": meta_dict.get("name", staged_path.name),
            "title": meta_dict.get("title", staged_path.name),
            "link": meta_dict.get("link", ""),
            "author": meta_dict.get("creator") or meta_dict.get("author", "Community"),
            "version": meta_dict.get("version", "1.0.0"),
            "image_url": meta_dict.get("image_url", ""),
            "category": meta_dict.get("category", "Other"),
            "description": meta_dict.get("description", ""),
            "fika_status": meta_dict.get("fika_status", "Unknown"),
            "source": meta_dict.get("source", "catalog" if meta_dict.get("link") else "local_archive_unlisted")
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def load_mod_meta(staged_path):
    if not staged_path:
        return None
    if staged_path.is_dir():
        meta_file = staged_path / ".meta.json"
    else:
        meta_file = staged_path.parent / f".{staged_path.name}.meta.json"
    if meta_file.exists():
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


class ModInstallerThread(QThread):
    finished = Signal(bool, str)

    def __init__(self, archive_path, mod_info=None):
        super().__init__()
        self.archive_path = Path(archive_path)
        self.mod_info = mod_info

    def _save_staged_metadata(self, target_staged):
        if not target_staged.is_dir():
            return
        meta = self.mod_info
        if not meta:
            matched = find_best_catalog_match_global(target_staged.name) or find_best_catalog_match_global(self.archive_path.name)
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
                    "source": "local_archive_matched"
                }
            else:
                clean_disp = re.sub(r'([a-z])([A-Z])', r'\1 \2', re.sub(r'\.dll$', '', target_staged.name, flags=re.I))
                meta = {
                    "name": target_staged.name,
                    "title": clean_disp,
                    "link": "",
                    "author": "Local Archive",
                    "version": "1.0.0",
                    "image_url": "",
                    "category": "Custom Local Mod",
                    "description": f"Locally installed archive package ({self.archive_path.name})",
                    "source": "local_archive_unlisted"
                }
        save_mod_meta(target_staged, meta)

    def run(self):
        try:
            temp_extract = DOWNLOADS_CACHE_DIR / f"temp_{self.archive_path.stem}"
            if temp_extract.exists():
                shutil.rmtree(temp_extract)
            temp_extract.mkdir(parents=True, exist_ok=True)

            if self.archive_path.suffix.lower() == ".zip":
                with zipfile.ZipFile(self.archive_path, 'r') as z:
                    z.extractall(temp_extract)
            elif self.archive_path.suffix.lower() == ".7z":
                res = subprocess.run(
                    ['7z', 'x', '-y', f'-o{temp_extract}', str(self.archive_path)],
                    capture_output=True, text=True
                )
                if res.returncode != 0:
                    self.finished.emit(False, f"7z Extraction error: {res.stderr}")
                    return
            else:
                self.finished.emit(False, "Unsupported archive format.")
                return

            bepin_src = None
            user_mods_src = None

            for p in temp_extract.rglob('*'):
                if p.is_dir():
                    if p.name.lower() == "plugins" and p.parent.name.lower() == "bepinex":
                        bepin_src = p
                    elif p.name.lower() == "mods" and p.parent.name.lower() == "user":
                        user_mods_src = p

            if bepin_src:
                for item in bepin_src.iterdir():
                    target_staged = STAGED_CLIENT / item.name
                    bak_path = target_staged.parent / f".{target_staged.name}.bak"

                    if bak_path.exists():
                        if bak_path.is_dir(): shutil.rmtree(bak_path)
                        else: bak_path.unlink()

                    if target_staged.exists():
                        target_staged.rename(bak_path)

                    try:
                        shutil.move(str(item), str(target_staged))
                        if bak_path.exists():
                            if bak_path.is_dir(): shutil.rmtree(bak_path)
                            else: bak_path.unlink()
                    except Exception as swap_err:
                        if bak_path.exists():
                            if target_staged.exists():
                                if target_staged.is_dir(): shutil.rmtree(target_staged)
                                else: target_staged.unlink()
                            bak_path.rename(target_staged)
                        raise swap_err

                    link_path = CLIENT_MODS_DIR / item.name
                    if link_path.exists() or link_path.is_symlink():
                        if link_path.is_dir() and not link_path.is_symlink(): shutil.rmtree(link_path)
                        else: link_path.unlink()
                    os.symlink(str(target_staged), str(link_path))
                    self._save_staged_metadata(target_staged)

            if user_mods_src:
                for item in user_mods_src.iterdir():
                    target_staged = STAGED_SERVER / item.name
                    bak_path = target_staged.parent / f".{target_staged.name}.bak"

                    if bak_path.exists():
                        if bak_path.is_dir(): shutil.rmtree(bak_path)
                        else: bak_path.unlink()

                    if target_staged.exists():
                        target_staged.rename(bak_path)

                    try:
                        shutil.move(str(item), str(target_staged))
                        if bak_path.exists():
                            if bak_path.is_dir(): shutil.rmtree(bak_path)
                            else: bak_path.unlink()
                    except Exception as swap_err:
                        if bak_path.exists():
                            if target_staged.exists():
                                if target_staged.is_dir(): shutil.rmtree(target_staged)
                                else: target_staged.unlink()
                            bak_path.rename(target_staged)
                        raise swap_err

                    link_path = SERVER_MODS_DIR / item.name
                    if link_path.exists() or link_path.is_symlink():
                        if link_path.is_dir() and not link_path.is_symlink(): shutil.rmtree(link_path)
                        else: link_path.unlink()
                    os.symlink(str(target_staged), str(link_path))
                    self._save_staged_metadata(target_staged)

            if not bepin_src and not user_mods_src:
                top_items = [p for p in temp_extract.iterdir() if not p.name.startswith('.')]
                for item in top_items:
                    is_server = (item / "package.json").exists() if item.is_dir() else False
                    target_staged_dir = STAGED_SERVER if is_server else STAGED_CLIENT
                    target_live_dir = SERVER_MODS_DIR if is_server else CLIENT_MODS_DIR

                    target_staged = target_staged_dir / item.name
                    if target_staged.exists():
                        if target_staged.is_dir(): shutil.rmtree(target_staged)
                        else: target_staged.unlink()
                    shutil.move(str(item), str(target_staged))

                    link_path = target_live_dir / item.name
                    if link_path.exists() or link_path.is_symlink():
                        if link_path.is_dir() and not link_path.is_symlink(): shutil.rmtree(link_path)
                        else: link_path.unlink()
                    os.symlink(str(target_staged), str(link_path))
                    self._save_staged_metadata(target_staged)

            if temp_extract.exists():
                shutil.rmtree(temp_extract)

            if DOWNLOADS_CACHE_DIR in self.archive_path.parents and self.archive_path.exists():
                try:
                    self.archive_path.unlink()
                except Exception:
                    pass

            self.finished.emit(True, f"Successfully staged & symlinked {self.archive_path.name}")
        except Exception as e:
            self.finished.emit(False, str(e))


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
                        if mod.get("client_staged"): save_mod_meta(mod["client_staged"], meta)
                        if mod.get("server_staged"): save_mod_meta(mod["server_staged"], meta)
                        self.updated.emit(name, f_stat)
                except Exception:
                    pass


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
            req = urllib.request.Request(
                self.download_url,
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
            )
            res = urllib.request.urlopen(req, timeout=15)
            
            disposition = res.headers.get("Content-Disposition", "")
            filename = None
            if "filename=" in disposition:
                filename = disposition.split("filename=")[-1].strip('"\'; ')

            if not filename:
                final_url = res.url
                filename = Path(final_url.split("?")[0]).name
                if not filename or filename == "download":
                    filename = f"{self.mod_title.replace(' ', '_')}.zip"

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
                        self.progress.emit(percent, f"Downloading... {downloaded//1024} KB / {total_bytes//1024} KB ({percent}%)")
                    else:
                        self.progress.emit(50, f"Downloading... {downloaded//1024} KB downloaded")

            self.progress.emit(100, f"Download Complete ({filename})")
            self.finished.emit(True, f"Successfully downloaded {filename}", target_file)
        except Exception as e:
            self.finished.emit(False, str(e), Path(""))


class StageInstallDialog(QDialog):
    def __init__(self, archive_path, mod_info, parent=None):
        super().__init__(parent)
        self.archive_path = Path(archive_path)
        self.mod_info = mod_info
        self.setWindowTitle(f"Stage & Install: {mod_info['title']}")
        self.resize(680, 500)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: #cdd6f4; }
            QLabel { color: #cdd6f4; }
            QTreeWidget { background-color: #181825; border: 1px solid #313244; color: #cdd6f4; }
            QHeaderView::section { background-color: #313244; color: #cdd6f4; font-weight: bold; }
            QPushButton { background-color: #313244; border: 1px solid #45475a; color: #cdd6f4; padding: 6px 14px; border-radius: 6px; }
            QPushButton:hover { background-color: #45475a; }
        """)

        layout = QVBoxLayout(self)

        lbl_header = QLabel(f"<b>Mod:</b> {mod_info['title']} <span style='color:#89b4fa;'>v{mod_info.get('version', '')}</span>")
        lbl_header.setFont(QFont("Ubuntu", 14, QFont.Bold))
        layout.addWidget(lbl_header)

        deps = mod_info.get("dependencies", [])
        if deps:
            for d in deps:
                d["installed"] = is_dependency_installed(d["title"])
            missing = [d for d in deps if not d.get("installed")]
            if missing:
                dep_box = QLabel(f"⚠️ <b>Warning:</b> This mod requires <b>{len(missing)} missing dependency mod(s)</b>: " + ", ".join(m['title'] for m in missing))
                dep_box.setStyleSheet("background-color: #313244; border: 1px solid #f38ba8; border-radius: 6px; padding: 8px; color: #f38ba8;")
                layout.addWidget(dep_box)
            else:
                dep_box = QLabel(f"✅ All <b>{len(deps)} required dependency mod(s)</b> are installed and enabled in your game.")
                dep_box.setStyleSheet("background-color: #181825; border: 1px solid #a6e3a1; border-radius: 6px; padding: 6px; color: #a6e3a1;")
                layout.addWidget(dep_box)

        size_mb = self.archive_path.stat().st_size / (1024 * 1024)
        lbl_info = QLabel(f"Downloaded Archive: <b>{self.archive_path.name}</b> ({size_mb:.2f} MB)")
        layout.addWidget(lbl_info)

        lbl_preview = QLabel("<b>Staged Package Contents:</b>")
        layout.addWidget(lbl_preview)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Target Destination", "Archive File / Path"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.tree)

        self.inspect_archive()

        btn_layout = QHBoxLayout()
        btn_open_folder = QPushButton("📁 Open Downloads Cache Folder")
        btn_open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(DOWNLOADS_CACHE_DIR))))
        btn_layout.addWidget(btn_open_folder)

        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_install = QPushButton("🚀 Install to SPT Now")
        btn_install.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold; font-size: 13px; padding: 8px 16px;")
        btn_install.clicked.connect(self.accept)
        btn_layout.addWidget(btn_install)

        layout.addLayout(btn_layout)

    def inspect_archive(self):
        self.tree.clear()
        try:
            if self.archive_path.suffix.lower() == ".zip":
                with zipfile.ZipFile(self.archive_path, 'r') as z:
                    for name in sorted(z.namelist()[:150]):
                        clean_name = name.replace('\\', '/')
                        target = "SPT Root"
                        if "bepinex" in clean_name.lower():
                            target = "Client (BepInEx/plugins)"
                        elif "user/mods" in clean_name.lower() or "spt_runtime" in clean_name.lower():
                            target = "Server (user/mods)"
                        item = QTreeWidgetItem([target, clean_name])
                        self.tree.addTopLevelItem(item)
            elif self.archive_path.suffix.lower() == ".7z":
                res = subprocess.run(['7z', 'l', str(self.archive_path)], capture_output=True, text=True)
                lines = res.stdout.splitlines()
                for line in lines[:80]:
                    if "---" in line or not line.strip():
                        continue
                    item = QTreeWidgetItem(["SPT Package", line.strip()])
                    self.tree.addTopLevelItem(item)
        except Exception as e:
            item = QTreeWidgetItem(["Error", str(e)])
            self.tree.addTopLevelItem(item)


def generate_html_stash_manifest(manifest):
    cards_html = ""
    for mod in manifest.get("mods", []):
        img_src = mod.get("image_url") or "https://files.sp-mod.com/mods/placeholder.png"
        title = html.escape(mod.get("title") or mod.get("name", "Unknown Mod"))
        author = html.escape(mod.get("author") or mod.get("creator", "Community"))
        ver = html.escape(str(mod.get("version", "")))
        cat = html.escape(mod.get("category", "General"))
        mod_type = html.escape(mod.get("type", "Mod"))
        raw_desc = mod.get("description", "")
        desc = html.escape(re.sub(r'<[^>]+>', '', raw_desc))[:240]
        if len(raw_desc) > 240:
            desc += "..."

        raw_link = mod.get("link")
        if not raw_link:
            query_name = urllib.parse.quote(mod.get("name", title))
            raw_link = f"https://sp-mod.com/mods?query={query_name}"
        link = html.escape(raw_link)

        img_tag = f'<img src="{img_src}" alt="{title}" loading="lazy" referrerpolicy="no-referrer" crossorigin="anonymous" onerror="this.onerror=null; this.style.display=\'none\';"/>' if img_src else ''

        cards_html += f"""
        <div class="card">
            {img_tag}
            <div class="card-body">
                <div class="title">{title}</div>
                <div class="author">by {author} • <span class="version">v{ver}</span></div>
                <div class="badges">
                    <span class="badge badge-type">{mod_type}</span>
                    <span class="badge badge-cat">{cat}</span>
                </div>
                <div class="desc">{desc}</div>
                <a class="btn" href="{link}" target="_blank">🔗 View on sp-mod.com</a>
            </div>
        </div>
        """

    json_data = json.dumps(manifest, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="referrer" content="no-referrer">
    <title>🎒 SPT Stash Manifest — {html.escape(manifest.get('spt_version', 'SPT'))}</title>
    <style>
        body {{ background-color: #11111b; color: #cdd6f4; font-family: 'Segoe UI', Ubuntu, Roboto, sans-serif; padding: 32px 20px; margin: 0; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ text-align: center; margin-bottom: 36px; border-bottom: 1px solid #313244; padding-bottom: 24px; }}
        .header h1 {{ color: #89b4fa; font-size: 32px; margin: 0 0 10px 0; font-weight: 800; }}
        .header p {{ color: #a6adc8; font-size: 15px; margin: 0; }}
        .meta-badges {{ margin-top: 14px; display: flex; justify-content: center; gap: 12px; flex-wrap: wrap; }}
        .meta-badge {{ background-color: #313244; color: #a6e3a1; padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 13px; }}
        .howto-box {{ background-color: #1e1e2e; border: 1px solid #89b4fa; border-radius: 12px; padding: 20px; margin-bottom: 32px; }}
        .howto-box h3 {{ color: #89b4fa; margin: 0 0 10px 0; font-size: 16px; display: flex; align-items: center; gap: 8px; }}
        .howto-box ol {{ margin: 0; padding-left: 20px; color: #cdd6f4; font-size: 14px; line-height: 1.6; }}
        .howto-box code {{ background-color: #313244; color: #a6e3a1; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 13px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 24px; }}
        .card {{ background-color: #181825; border: 1px solid #313244; border-radius: 14px; overflow: hidden; display: flex; flex-direction: column; transition: transform 0.2s, border-color 0.2s; }}
        .card:hover {{ transform: translateY(-4px); border-color: #89b4fa; }}
        .card img {{ width: 100%; height: 170px; object-fit: cover; background-color: #1e1e2e; }}
        .card-body {{ padding: 18px; display: flex; flex-direction: column; flex-grow: 1; }}
        .title {{ color: #89b4fa; font-size: 18px; font-weight: bold; margin-bottom: 4px; line-height: 1.3; }}
        .author {{ color: #9399b2; font-size: 13px; margin-bottom: 10px; }}
        .version {{ color: #fab387; font-weight: bold; }}
        .badges {{ margin-bottom: 12px; display: flex; gap: 8px; flex-wrap: wrap; }}
        .badge {{ padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: bold; }}
        .badge-type {{ background-color: #313244; color: #cba6f7; }}
        .badge-cat {{ background-color: #313244; color: #89dceb; }}
        .desc {{ font-size: 13px; color: #bac2de; line-height: 1.5; flex-grow: 1; margin-bottom: 16px; }}
        .btn {{ display: block; text-align: center; background-color: #89b4fa; color: #11111b; text-decoration: none; padding: 10px; border-radius: 8px; font-weight: bold; font-size: 13px; transition: background-color 0.2s; }}
        .btn:hover {{ background-color: #b4befe; }}
        .footer {{ text-align: center; margin-top: 40px; color: #6c7086; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎒 SPT Stash Manifest</h1>
            <p>Single-Player Tarkov Co-Op & Raid Mod Loadout</p>
            <div class="meta-badges">
                <span class="meta-badge">Target: {html.escape(manifest.get('spt_version', 'SPT'))}</span>
                <span class="meta-badge">📦 {manifest.get('total_packages', len(manifest.get('mods', [])))} Mod Packages</span>
                <span class="meta-badge">📁 {manifest.get('total_files', len(manifest.get('mods', [])))} Component Files</span>
            </div>
        </div>
        <div class="howto-box">
            <h3>💡 Quick Import Instructions for SPT Stash</h3>
            <ol>
                <li>Launch <b>SPT Stash</b> on your system.</li>
                <li>Go to the <b>🎒 Presets & Manifests</b> tab (or <b>Installed Mods</b> tab).</li>
                <li>Click <b>📥 Import Preset File</b> and select this file (<code id="manifest-filename">stash_manifest.html</code>).</li>
                <li>Click <b>▶ Apply Preset to Game</b> — <b>SPT Stash</b> will instantly enable all included mods and 1-click download any missing ones!</li>
            </ol>
        </div>
        <div class="grid">
            {cards_html}
        </div>
        <div class="footer">
            Generated by <b>SPT Stash</b> — Native Linux Mod Manager for SPTarkov
        </div>
    </div>
    <script>
    document.addEventListener("DOMContentLoaded", function() {{
        var filename = window.location.pathname.split('/').pop() || "stash_manifest.html";
        var el = document.getElementById("manifest-filename");
        if (el) el.textContent = decodeURIComponent(filename);
    }});
    </script>
    <script id="stash-manifest-data" type="application/json">
{json_data}
    </script>
</body>
</html>"""


def load_config():
    defaults = {
        "spt_path": str(find_spt_root()),
        "staged_dir": str(Path.home() / ".local" / "share" / "spt-mod-manager" / "staged"),
        "server_script": str(find_spt_root() / "server.sh"),
        "launcher_script": str(find_spt_root() / "launcher.sh")
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
                defaults.update(cfg)
        except Exception:
            pass
    return defaults


def save_config(cfg_dict):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg_dict, f, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}")


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ SPT Stash Settings")
        self.resize(650, 420)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: #cdd6f4; }
            QLabel { color: #cdd6f4; font-weight: bold; font-size: 13px; }
            QLineEdit { background-color: #313244; border: 1px solid #45475a; color: #cdd6f4; padding: 6px; border-radius: 6px; }
            QPushButton { background-color: #313244; border: 1px solid #45475a; color: #cdd6f4; padding: 6px 14px; border-radius: 6px; }
            QPushButton:hover { background-color: #45475a; }
        """)

        layout = QVBoxLayout(self)

        self.cfg = load_config()

        # SPT Path
        lbl_spt = QLabel("SPT Installation Folder:")
        lbl_spt_help = QLabel("<small style='color: #a6adc8;'>Root directory containing server.sh, launcher.sh, BepInEx, and SPT_Runtime (e.g. ~/Games/SPT). Do NOT select Wine/Proton prefix.</small>")
        lbl_spt_help.setWordWrap(True)
        spt_layout = QHBoxLayout()
        self.txt_spt = QLineEdit(self.cfg.get("spt_path", ""))
        self.txt_spt.setToolTip("Select the root directory where Single-Player Tarkov (SPT) is installed (e.g. ~/Games/SPT).")
        btn_browse_spt = QPushButton("Browse...")
        btn_browse_spt.clicked.connect(self.browse_spt_folder)
        spt_layout.addWidget(self.txt_spt)
        spt_layout.addWidget(btn_browse_spt)
        layout.addWidget(lbl_spt)
        layout.addWidget(lbl_spt_help)
        layout.addLayout(spt_layout)

        # Staged Directory
        lbl_staged = QLabel("Mod Staging Stash Directory:")
        lbl_staged_help = QLabel("<small style='color: #a6adc8;'>Local directory where SPT Stash downloads and stages mods before symlinking into the game.</small>")
        lbl_staged_help.setWordWrap(True)
        staged_layout = QHBoxLayout()
        self.txt_staged = QLineEdit(self.cfg.get("staged_dir", ""))
        self.txt_staged.setToolTip("Directory where SPT Stash stores downloaded and extracted mod files.")
        btn_browse_staged = QPushButton("Browse...")
        btn_browse_staged.clicked.connect(self.browse_staged_folder)
        staged_layout.addWidget(self.txt_staged)
        staged_layout.addWidget(btn_browse_staged)
        layout.addWidget(lbl_staged)
        layout.addWidget(lbl_staged_help)
        layout.addLayout(staged_layout)

        # Server Script Path
        lbl_server = QLabel("Start Server Script Path:")
        lbl_server_help = QLabel("<small style='color: #a6adc8;'>Path to server.sh (or SPT.Server.exe) used to launch the SPT server process.</small>")
        lbl_server_help.setWordWrap(True)
        server_layout = QHBoxLayout()
        self.txt_server = QLineEdit(self.cfg.get("server_script", ""))
        self.txt_server.setToolTip("Executable path to server.sh or SPT.Server.exe.")
        btn_browse_server = QPushButton("Browse...")
        btn_browse_server.clicked.connect(self.browse_server_script)
        server_layout.addWidget(self.txt_server)
        server_layout.addWidget(btn_browse_server)
        layout.addWidget(lbl_server)
        layout.addWidget(lbl_server_help)
        layout.addLayout(server_layout)

        # Launcher Script Path
        lbl_launcher = QLabel("Launch SPT / Launcher Script Path:")
        lbl_launcher_help = QLabel("<small style='color: #a6adc8;'>Path to launcher.sh (or SPT.Launcher.exe) used to launch the game.</small>")
        lbl_launcher_help.setWordWrap(True)
        launcher_layout = QHBoxLayout()
        self.txt_launcher = QLineEdit(self.cfg.get("launcher_script", ""))
        self.txt_launcher.setToolTip("Executable path to launcher.sh or SPT.Launcher.exe.")
        btn_browse_launcher = QPushButton("Browse...")
        btn_browse_launcher.clicked.connect(self.browse_launcher_script)
        launcher_layout.addWidget(self.txt_launcher)
        launcher_layout.addWidget(btn_browse_launcher)
        layout.addWidget(lbl_launcher)
        layout.addWidget(lbl_launcher_help)
        layout.addLayout(launcher_layout)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("💾 Save Settings")
        btn_save.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold; padding: 6px 16px;")
        btn_save.clicked.connect(self.save_settings)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def browse_spt_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select SPT Installation Folder", self.txt_spt.text())
        if dir_path:
            self.txt_spt.setText(dir_path)

    def browse_staged_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Mod Staging Stash Directory", self.txt_staged.text())
        if dir_path:
            self.txt_staged.setText(dir_path)

    def browse_server_script(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Server Script", self.txt_server.text(), "Scripts (*.sh *.exe);;All Files (*)")
        if file_path:
            self.txt_server.setText(file_path)

    def browse_launcher_script(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Launcher Script", self.txt_launcher.text(), "Scripts (*.sh *.exe);;All Files (*)")
        if file_path:
            self.txt_launcher.setText(file_path)

    def save_settings(self):
        spt = self.txt_spt.text().strip()
        staged = self.txt_staged.text().strip()
        server = self.txt_server.text().strip()
        launcher = self.txt_launcher.text().strip()

        if not spt or not staged or not server or not launcher:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("⚠️ Missing Required Paths")
            msg.setText("<b>All path settings fields are required.</b><br><br>Please ensure no path field is left blank before saving settings.")
            msg.setStyleSheet("""
                QMessageBox { background-color: #1e1e2e; color: #cdd6f4; }
                QLabel { color: #cdd6f4; min-width: 380px; font-size: 13px; }
                QPushButton { background-color: #313244; border: 1px solid #45475a; color: #cdd6f4; padding: 6px 14px; border-radius: 6px; }
                QPushButton:hover { background-color: #45475a; }
            """)
            msg.exec()
            return

        self.cfg["spt_path"] = spt
        self.cfg["staged_dir"] = staged
        self.cfg["server_script"] = server
        self.cfg["launcher_script"] = launcher
        save_config(self.cfg)
        self.accept()


class ModItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 58)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        rect = option.rect.adjusted(4, 2, -4, -2)
        mod = index.data(Qt.UserRole)
        is_selected = bool(option.state & QStyle.State_Selected)
        is_hovered = bool(option.state & QStyle.State_MouseOver)

        if not mod:
            painter.restore()
            return

        status, _ = check_dep_status(mod.get('title', ''))

        if status == "ENABLED":
            bg_color = QColor('#1e3a29') if not is_selected else QColor('#2b4c37')
            border_color = QColor('#a6e3a1')
        elif status == "STAGED_DISABLED":
            bg_color = QColor('#3a2c1e') if not is_selected else QColor('#4c3a27')
            border_color = QColor('#fab387')
        elif is_selected:
            bg_color = QColor('#313244')
            border_color = QColor('#89b4fa')
        elif is_hovered:
            bg_color = QColor('#262637')
            border_color = QColor('#45475a')
        else:
            bg_color = QColor('#181825')
            border_color = QColor('#262637')

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1.5 if (is_selected or status != "MISSING") else 1.0))
        painter.drawRoundedRect(rect, 8, 8)

        font_title = QFont('Ubuntu', 11, QFont.Bold)
        painter.setFont(font_title)
        painter.setPen(QPen(QColor('#a6e3a1') if status == "ENABLED" else (QColor('#fab387') if status == "STAGED_DISABLED" else (QColor('#89b4fa') if is_selected else QColor('#cdd6f4')))))

        title = mod.get('title', 'Unknown')
        title_rect = rect.adjusted(12, 6, -140, -26)
        metrics = painter.fontMetrics()
        elided_title = metrics.elidedText(title, Qt.ElideRight, max(50, title_rect.width()))
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_title)

        font_sub = QFont('Ubuntu', 9)
        painter.setFont(font_sub)
        painter.setPen(QPen(QColor('#bac2de') if is_selected else QColor('#a6adc8')))

        author = mod.get('creator', 'Community')
        ver = mod.get('version', '')
        spt_ver = mod.get('spt_version', '')
        f_stat = mod.get('fika_status', '')

        sub_text = f"by {author}"
        if ver: sub_text += f"  •  v{ver}"
        if spt_ver: sub_text += f"  •  {spt_ver}"
        if "Compatible" in f_stat or f_stat == "Yes":
            sub_text += "  •  🟢 Fika"
        if status == "ENABLED":
            sub_text += "  •  ✅ Installed"
        elif status == "STAGED_DISABLED":
            sub_text += "  •  ⚠️ Stashed (Disabled)"

        sub_rect = rect.adjusted(12, 28, -140, -6)
        elided_sub = metrics.elidedText(sub_text, Qt.ElideRight, max(50, sub_rect.width()))
        painter.drawText(sub_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_sub)

        dl_cnt = mod.get('downloads', 0)
        end_cnt = mod.get('endorsements', 0)
        stats_str = ""
        if dl_cnt: stats_str += f"📥 {dl_cnt:,} "
        if end_cnt: stats_str += f"👍 {end_cnt}"

        if stats_str:
            painter.setFont(QFont('Ubuntu', 9, QFont.Bold))
            painter.setPen(QPen(QColor('#a6e3a1') if is_selected else QColor('#fab387')))
            painter.drawText(rect.adjusted(-12, 0, -12, 0), Qt.AlignRight | Qt.AlignVCenter, stats_str.strip())

        painter.restore()


class SavePresetDialog(QDialog):
    def __init__(self, enabled_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Preset — SPT Stash")
        self.setMinimumWidth(440)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: #cdd6f4; font-family: 'Segoe UI', Ubuntu, sans-serif; }
            QLabel { color: #cdd6f4; font-size: 13px; }
            QLineEdit { background-color: #181825; border: 1px solid #45475a; border-radius: 6px; color: #cdd6f4; padding: 8px 12px; font-size: 13px; }
            QPushButton { background-color: #313244; border: 1px solid #45475a; color: #cdd6f4; padding: 8px 16px; border-radius: 6px; font-weight: 500; font-size: 13px; }
            QPushButton:hover { background-color: #45475a; }
            QPushButton#btnSave { background-color: #a6e3a1; color: #11111b; font-weight: bold; border: 1px solid #a6e3a1; }
        """)

        layout = QVBoxLayout(self)

        title_lbl = QLabel("🎒 Create New Stash Preset")
        title_lbl.setFont(QFont("Ubuntu", 14, QFont.Bold))
        layout.addWidget(title_lbl)

        sub_lbl = QLabel(f"This will snapshot your <b>{enabled_count} currently enabled mod(s)</b>.")
        sub_lbl.setStyleSheet("color: #a6adc8; margin-bottom: 12px;")
        layout.addWidget(sub_lbl)

        layout.addWidget(QLabel("Preset Name:"))
        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("e.g. Fika Co-Op Raid Loadout")
        layout.addWidget(self.txt_title)

        layout.addWidget(QLabel("Short Description (Optional):"))
        self.txt_desc = QLineEdit()
        self.txt_desc.setPlaceholderText("e.g. SAIN AI, UI Fixes, and Fika Server")
        layout.addWidget(self.txt_desc)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("💾 Save Preset")
        btn_save.setObjectName("btnSave")
        btn_save.clicked.connect(self.accept)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def get_data(self):
        return self.txt_title.text().strip(), self.txt_desc.text().strip()


class SPTModManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SPT Stash — Mod Manager for Single-Player Tarkov")
        self.resize(1150, 720)

        # Style
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
            QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Segoe UI', Ubuntu, sans-serif;
                font-size: 13px;
            }
            QGroupBox {
                border: 1px solid #45475a;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                color: #cba6f7;
            }
            QTabWidget::pane {
                border: 1px solid #313244;
                background: #181825;
                border-radius: 6px;
            }
            QTabBar::tab {
                background: #313244;
                color: #a6adc8;
                padding: 8px 18px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background: #89b4fa;
                color: #11111b;
            }
            QPushButton {
                background-color: #313244;
                border: 1px solid #45475a;
                color: #cdd6f4;
                padding: 6px 14px;
                border-radius: 6px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #45475a;
                border-color: #585b70;
            }
            QPushButton#btnLaunch {
                background-color: #27392b;
                color: #a6e3a1;
                border: 1px solid #36503c;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton#btnLaunch:hover {
                background-color: #314a38;
                border-color: #a6e3a1;
            }
            QPushButton#btnStop {
                background-color: #3a232e;
                color: #f38ba8;
                border: 1px solid #542f3e;
                font-weight: bold;
            }
            QPushButton#btnStop:hover {
                background-color: #4a2c3b;
                border-color: #f38ba8;
            }
            QLineEdit, QComboBox {
                background-color: #313244;
                border: 1px solid #45475a;
                color: #cdd6f4;
                padding: 6px;
                border-radius: 6px;
            }
            QTableWidget, QListWidget {
                background-color: #181825;
                border: 1px solid #313244;
                gridline-color: #313244;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #313244;
                color: #cdd6f4;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
            QTextBrowser {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 6px;
                color: #cdd6f4;
            }
        """)

        self.remote_mods = []

        self.init_ui()
        self.check_server_status()

        # Timer for server status check
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.check_server_status)
        self.status_timer.start(3000)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # Header Bar
        header_layout = QHBoxLayout()
        
        title_label = QLabel("🎒 SPT Stash")
        title_label.setFont(QFont("Ubuntu", 17, QFont.Bold))
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.status_badge = QLabel("Server: Unknown")
        self.status_badge.setStyleSheet("padding: 4px 10px; border-radius: 12px; background-color: #45475a; font-weight: bold;")
        header_layout.addWidget(self.status_badge)

        self.btn_server_control = QPushButton("▶ Start Server")
        self.btn_server_control.clicked.connect(self.toggle_server_control)
        header_layout.addWidget(self.btn_server_control)

        self.btn_launch = QPushButton("▶ Launch SPT")
        self.btn_launch.setObjectName("btnLaunch")
        self.btn_launch.clicked.connect(self.launch_spt)
        header_layout.addWidget(self.btn_launch)

        self.btn_settings = QPushButton("⚙️ Settings")
        self.btn_settings.clicked.connect(self.open_settings_dialog)
        header_layout.addWidget(self.btn_settings)

        main_layout.addLayout(header_layout)

        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.tab_installed = QWidget()
        self.tab_presets = QWidget()
        self.tab_browse = QWidget()
        self.tab_installer = QWidget()
        self.tab_performance = QWidget()

        self.tabs.addTab(self.tab_installed, "Installed Mods")
        self.tabs.addTab(self.tab_presets, "🎒 Presets && Manifests")
        self.tabs.addTab(self.tab_browse, "Browse sp-mod.com (Forge)")
        self.tabs.addTab(self.tab_installer, "Install Local Mod Archive")
        self.tabs.addTab(self.tab_performance, "⚡ Linux Performance")

        self.setup_installed_tab()
        self.setup_presets_tab()
        self.setup_browse_tab()
        self.setup_installer_tab()
        self.setup_performance_tab()

    # ------------------ Installed Mods Tab ------------------
    def setup_installed_tab(self):
        layout = QVBoxLayout(self.tab_installed)

        top_controls = QHBoxLayout()
        self.installed_search = QLineEdit()
        self.installed_search.setPlaceholderText("Filter installed mods...")
        self.installed_search.textChanged.connect(self.filter_installed_mods)
        top_controls.addWidget(self.installed_search)

        btn_check_updates = QPushButton("🔄 Check for Updates")
        btn_check_updates.clicked.connect(lambda: self.check_installed_mod_updates())
        top_controls.addWidget(btn_check_updates)

        btn_audit = QPushButton("🔍 Audit Dependencies")
        btn_audit.clicked.connect(self.audit_installed_dependencies)
        top_controls.addWidget(btn_audit)

        btn_refresh = QPushButton("🔄 Refresh Installed Mods")
        btn_refresh.clicked.connect(self.load_installed_mods)
        top_controls.addWidget(btn_refresh)

        btn_export = QPushButton("📤 Export Manifest")
        btn_export.clicked.connect(self.export_stash_manifest)
        top_controls.addWidget(btn_export)

        btn_import = QPushButton("📥 Import Manifest")
        btn_import.clicked.connect(self.import_stash_manifest)
        top_controls.addWidget(btn_import)

        btn_install = QPushButton("➕ Install Archive (.zip/.7z)")
        btn_install.clicked.connect(self.open_file_installer)
        top_controls.addWidget(btn_install)

        layout.addLayout(top_controls)

        self.table_mods = QTableWidget()
        self.table_mods.setColumnCount(7)
        self.table_mods.setHorizontalHeaderLabels(["Status", "Mod Name", "Version", "Type", "Fika Co-Op", "Author", "Actions"])
        self.table_mods.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_mods.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_mods.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_mods.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_mods.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_mods.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table_mods.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)
        self.table_mods.setColumnWidth(6, 185)
        self.table_mods.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_mods.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_mods.setSortingEnabled(True)
        self.table_mods.horizontalHeader().setSortIndicatorShown(True)
        self.table_mods.horizontalHeader().setSectionsClickable(True)
        self.table_mods.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_mods.customContextMenuRequested.connect(self.show_installed_table_context_menu)
        self.table_mods.cellClicked.connect(self.on_installed_table_cell_clicked)
        self.table_mods.itemSelectionChanged.connect(self.update_bulk_actions_bar)
        layout.addWidget(self.table_mods)

        # Bulk Actions Bar
        bulk_bar = QHBoxLayout()

        self.lbl_selected_count = QLabel("0 mod(s) selected")
        self.lbl_selected_count.setStyleSheet("color: #a6adc8; font-weight: bold; padding: 4px 8px;")
        bulk_bar.addWidget(self.lbl_selected_count)

        btn_style_base = "font-size: 13px; font-weight: bold; padding: 6px 14px; border-radius: 6px; height: 32px;"

        btn_select_all = QPushButton("☑️ Select All")
        btn_select_all.setFixedHeight(36)
        btn_select_all.clicked.connect(lambda: self.select_all_installed_mods())
        bulk_bar.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("☐ Deselect All")
        btn_deselect_all.setFixedHeight(36)
        btn_deselect_all.clicked.connect(lambda: self.deselect_all_installed_mods())
        bulk_bar.addWidget(btn_deselect_all)

        bulk_bar.addStretch()

        self.btn_bulk_enable = QPushButton("▶ Enable Selected")
        self.btn_bulk_enable.setFixedHeight(36)
        self.btn_bulk_enable.setFixedWidth(160)
        self.btn_bulk_enable.setStyleSheet("""
            QPushButton { background-color: #27392b; color: #a6e3a1; border: 1px solid #36503c; font-size: 13px; font-weight: bold; border-radius: 6px; }
            QPushButton:hover { background-color: #314a38; border-color: #a6e3a1; }
            QPushButton:disabled { background-color: #1e1e2e; color: #585b70; border: 1px solid #313244; }
        """)
        self.btn_bulk_enable.clicked.connect(lambda: self.bulk_enable_selected())
        self.btn_bulk_enable.setEnabled(False)
        bulk_bar.addWidget(self.btn_bulk_enable)

        self.btn_bulk_disable = QPushButton("⏸ Disable Selected")
        self.btn_bulk_disable.setFixedHeight(36)
        self.btn_bulk_disable.setFixedWidth(160)
        self.btn_bulk_disable.setStyleSheet("""
            QPushButton { background-color: #3b2d24; color: #fab387; border: 1px solid #543f31; font-size: 13px; font-weight: bold; border-radius: 6px; }
            QPushButton:hover { background-color: #4a392e; border-color: #fab387; }
            QPushButton:disabled { background-color: #1e1e2e; color: #585b70; border: 1px solid #313244; }
        """)
        self.btn_bulk_disable.clicked.connect(lambda: self.bulk_disable_selected())
        self.btn_bulk_disable.setEnabled(False)
        bulk_bar.addWidget(self.btn_bulk_disable)

        self.btn_bulk_delete = QPushButton("🗑 Delete Selected")
        self.btn_bulk_delete.setFixedHeight(36)
        self.btn_bulk_delete.setFixedWidth(160)
        self.btn_bulk_delete.setStyleSheet("""
            QPushButton { background-color: #3a232e; color: #f38ba8; border: 1px solid #542f3e; font-size: 13px; font-weight: bold; border-radius: 6px; }
            QPushButton:hover { background-color: #4a2c3b; border-color: #f38ba8; }
            QPushButton:disabled { background-color: #1e1e2e; color: #585b70; border: 1px solid #313244; }
        """)
        self.btn_bulk_delete.clicked.connect(lambda: self.bulk_delete_selected())
        self.btn_bulk_delete.setEnabled(False)
        bulk_bar.addWidget(self.btn_bulk_delete)

        layout.addLayout(bulk_bar)

        self.load_installed_mods()

    def load_installed_mods(self):
        self.table_mods.setRowCount(0)
        mods_map = {}

        client_items = list(STAGED_CLIENT.iterdir()) if STAGED_CLIENT.exists() else []
        server_items = list(STAGED_SERVER.iterdir()) if STAGED_SERVER.exists() else []

        def get_mod_group_key(item):
            meta = load_mod_meta(item) or {}
            matched = find_best_catalog_match_global(item.name)

            if matched and matched.get("title"):
                official_title = matched.get("title").strip()
                if meta.get("title") != official_title or not meta.get("link"):
                    meta["title"] = official_title
                    meta["link"] = matched.get("link", meta.get("link", ""))
                    meta["author"] = matched.get("creator", meta.get("author", ""))
                    meta["version"] = matched.get("version", meta.get("version", "1.0.0"))
                    save_mod_meta(item, meta)
                return official_title.lower(), official_title

            if meta.get("title"):
                return meta.get("title").strip().lower(), meta.get("title").strip()

            clean = re.sub(r'(\.dll|\.Server|ServerMod|Server|\.Client|Client)$', '', item.name, flags=re.I).strip()
            return clean.lower(), item.name

        for item in client_items:
            if item.name.startswith('.'):
                continue
            key, display_name = get_mod_group_key(item)
            live_link = CLIENT_MODS_DIR / item.name
            is_enabled = live_link.is_symlink() or live_link.exists()

            if key not in mods_map:
                mods_map[key] = {
                    "name": display_name,
                    "has_client": True,
                    "has_server": False,
                    "client_items": [(item, live_link, is_enabled)],
                    "server_items": []
                }
            else:
                mods_map[key]["has_client"] = True
                mods_map[key]["client_items"].append((item, live_link, is_enabled))

        for item in server_items:
            if item.name.startswith('.'):
                continue
            key, display_name = get_mod_group_key(item)
            live_link = SERVER_MODS_DIR / item.name
            is_enabled = live_link.is_symlink() or live_link.exists()

            if key not in mods_map:
                mods_map[key] = {
                    "name": display_name,
                    "has_client": False,
                    "has_server": True,
                    "client_items": [],
                    "server_items": [(item, live_link, is_enabled)]
                }
            else:
                mods_map[key]["has_server"] = True
                mods_map[key]["server_items"].append((item, live_link, is_enabled))

        mods = []
        for key in sorted(list(mods_map.keys())):
            m = mods_map[key]
            c_on = any(p[2] for p in m["client_items"]) if m["has_client"] else False
            s_on = any(p[2] for p in m["server_items"]) if m["has_server"] else False

            if m["has_client"] and m["has_server"]:
                m_type = "Dual (Client + Server)"
                disabled = not (c_on or s_on)
            elif m["has_client"]:
                m_type = "Client (BepInEx)"
                disabled = not c_on
            else:
                m_type = "Server (user/mods)"
                disabled = not s_on

            m["type"] = m_type
            m["disabled"] = disabled

            first_client = m["client_items"][0][0] if m["client_items"] else None
            first_server = m["server_items"][0][0] if m["server_items"] else None

            m["client_staged"] = first_client
            m["server_staged"] = first_server
            m["staged_path"] = first_client or first_server
            m["live_path"] = (m["client_items"][0][1] if m["client_items"] else None) or (m["server_items"][0][1] if m["server_items"] else None)
            mods.append(m)

        self.all_installed_mods = mods
        self.filter_installed_mods(self.installed_search.text())

        if hasattr(self, 'list_presets') and self.list_presets.currentItem():
            self.on_preset_selected()

    def render_installed_mods(self, mods):
        self.table_mods.setSortingEnabled(False)
        self.table_mods.setRowCount(0)
        unknown_fika_mods = []

        for mod in mods:
            row = self.table_mods.rowCount()
            self.table_mods.insertRow(row)
            self.table_mods.setRowHeight(row, 40)

            status_str = "❌ Disabled" if mod["disabled"] else "✅ Enabled"
            item_status = QTableWidgetItem(status_str)
            item_status.setForeground(QColor("#f38ba8") if mod["disabled"] else QColor("#a6e3a1"))
            self.table_mods.setItem(row, 0, item_status)

            item_name = QTableWidgetItem(mod["name"])
            item_name.setData(Qt.UserRole, mod)
            self.table_mods.setItem(row, 1, item_name)

            # Metadata resolution for Version & Fika
            meta = load_mod_meta(mod["staged_path"]) or {}
            ver_str = meta.get("version")
            if not ver_str and mod.get("has_server") and mod.get("server_staged"):
                server_meta = load_mod_meta(mod["server_staged"]) or {}
                ver_str = server_meta.get("version")

            if not ver_str:
                matched = find_best_catalog_match_global(mod["name"])
                if matched: ver_str = matched.get("version")
            if not ver_str: ver_str = "1.0.0"

            display_ver = f"v{ver_str}" if not str(ver_str).startswith("v") else str(ver_str)
            item_ver = QTableWidgetItem(display_ver)
            item_ver.setForeground(QColor("#fab387"))
            self.table_mods.setItem(row, 2, item_ver)

            self.table_mods.setItem(row, 3, QTableWidgetItem(mod["type"]))

            # Fika status
            f_stat = meta.get("fika_status")

            if not f_stat and mod.get("has_server") and mod.get("server_staged"):
                server_meta = load_mod_meta(mod["server_staged"]) or {}
                f_stat = server_meta.get("fika_status")

            if not f_stat or f_stat == "Unknown":
                matched = find_best_catalog_match_global(mod["name"])
                if matched and matched.get("fika_status") and matched.get("fika_status") != "Unknown":
                    f_stat = matched.get("fika_status")
                    meta["fika_status"] = f_stat
                    if mod.get("client_staged"): save_mod_meta(mod["client_staged"], meta)
                    if mod.get("server_staged"): save_mod_meta(mod["server_staged"], meta)
                else:
                    unknown_fika_mods.append(mod)

            if not f_stat:
                f_stat = "Unknown"

            if "Compatible" in f_stat or f_stat == "Yes":
                item_fika = QTableWidgetItem("🟢 Compatible")
                item_fika.setForeground(QColor("#a6e3a1"))
            elif "Incompatible" in f_stat or f_stat == "No":
                item_fika = QTableWidgetItem("🔴 Incompatible")
                item_fika.setForeground(QColor("#f38ba8"))
            else:
                item_fika = QTableWidgetItem("🟡 Unknown")
                item_fika.setForeground(QColor("#fab387"))

            self.table_mods.setItem(row, 4, item_fika)

            # Author column as underlined hyperlink
            author_str = meta.get("author")
            if not author_str or author_str == "Community":
                matched = find_best_catalog_match_global(mod["name"])
                if matched and matched.get("creator"):
                    author_str = matched.get("creator")
            if not author_str:
                author_str = "Community"

            item_author = QTableWidgetItem(f"by {author_str}")
            font_author = item_author.font()
            font_author.setUnderline(True)
            item_author.setFont(font_author)
            item_author.setForeground(QColor("#89b4fa"))
            item_author.setToolTip(f"Open {author_str}'s profile on sp-mod.com")
            self.table_mods.setItem(row, 5, item_author)

            # Action buttons widget
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 2, 2, 2)
            action_layout.setSpacing(4)

            if not mod["disabled"]:
                btn_toggle = QPushButton("Disable")
                btn_toggle.setMinimumWidth(75)
                btn_toggle.setStyleSheet("""
                    QPushButton { background-color: #3b2d24; color: #fab387; border: 1px solid #543f31; font-weight: bold; border-radius: 4px; }
                    QPushButton:hover { background-color: #4a392e; border-color: #fab387; }
                """)
            else:
                btn_toggle = QPushButton("Enable")
                btn_toggle.setMinimumWidth(75)
                btn_toggle.setStyleSheet("""
                    QPushButton { background-color: #27392b; color: #a6e3a1; border: 1px solid #36503c; font-weight: bold; border-radius: 4px; }
                    QPushButton:hover { background-color: #314a38; border-color: #a6e3a1; }
                """)

            btn_toggle.clicked.connect(lambda _, m=mod: self.toggle_mod(m))
            action_layout.addWidget(btn_toggle)

            btn_del = QPushButton("Delete")
            btn_del.setMinimumWidth(70)
            btn_del.setStyleSheet("""
                QPushButton { background-color: #3a232e; color: #f38ba8; border: 1px solid #542f3e; font-weight: bold; border-radius: 4px; }
                QPushButton:hover { background-color: #4a2c3b; border-color: #f38ba8; }
            """)
            btn_del.clicked.connect(lambda _, m=mod: self.delete_mod(m))
            action_layout.addWidget(btn_del)

            self.table_mods.setCellWidget(row, 6, action_widget)

        self.table_mods.setSortingEnabled(True)
        self.update_bulk_actions_bar()

        if unknown_fika_mods:
            self.fika_sync_thread = FikaSyncThread(unknown_fika_mods, self)
            self.fika_sync_thread.updated.connect(self.on_fika_updated)
            self.fika_sync_thread.start()

    def on_fika_updated(self, mod_name, fika_status):
        for row in range(self.table_mods.rowCount()):
            item_name = self.table_mods.item(row, 1)
            if item_name and item_name.text().lower() == mod_name.lower():
                if "Compatible" in fika_status or fika_status == "Yes":
                    item_fika = QTableWidgetItem("🟢 Compatible")
                    item_fika.setForeground(QColor("#a6e3a1"))
                elif "Incompatible" in fika_status or fika_status == "No":
                    item_fika = QTableWidgetItem("🔴 Incompatible")
                    item_fika.setForeground(QColor("#f38ba8"))
                else:
                    item_fika = QTableWidgetItem("🟡 Unknown")
                    item_fika.setForeground(QColor("#fab387"))
                self.table_mods.setItem(row, 4, item_fika)

    def on_installed_table_cell_clicked(self, row, col):
        if col == 5:
            mod_item = self.table_mods.item(row, 1)
            if mod_item:
                mod = mod_item.data(Qt.UserRole)
                if mod:
                    url = resolve_author_profile_url(mod)
                    QDesktopServices.openUrl(QUrl(url))

    def show_installed_table_context_menu(self, pos):
        item = self.table_mods.itemAt(pos)
        if not item:
            return
        row = item.row()
        mod_item = self.table_mods.item(row, 1)
        if not mod_item:
            return
        mod = mod_item.data(Qt.UserRole)
        if not mod:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1e1e2e; color: #cdd6f4; border: 1px solid #45475a; border-radius: 8px; padding: 6px; }
            QMenu::item { padding: 8px 24px; border-radius: 4px; font-weight: 500; }
            QMenu::item:selected { background-color: #313244; color: #89b4fa; }
            QMenu::separator { height: 1px; background-color: #313244; margin: 4px 0px; }
        """)

        act_open_folder = menu.addAction("📁 Open Folder in File Manager")
        act_open_web = menu.addAction("🔗 Open Web Page on sp-mod.com")
        
        meta = load_mod_meta(mod["staged_path"]) or {}
        author_str = meta.get("author")
        if not author_str or author_str == "Community":
            matched = find_best_catalog_match_global(mod["name"])
            if matched: author_str = matched.get("creator")

        act_author_search = None
        if author_str and author_str != "Community":
            act_author_search = menu.addAction(f"👤 Open {author_str}'s Profile on sp-mod.com")

        menu.addSeparator()

        is_disabled = mod.get("disabled", False)
        act_toggle = menu.addAction("⚡ Enable Mod" if is_disabled else "⏸ Disable Mod")
        act_check_upd = menu.addAction("🔄 Check for Updates")
        menu.addSeparator()

        act_copy_path = menu.addAction("📋 Copy Path to Clipboard")
        menu.addSeparator()

        act_delete = menu.addAction("🗑 Delete Mod Package")

        global_pos = self.table_mods.viewport().mapToGlobal(pos)
        action = menu.exec(global_pos)
        if not action:
            return

        if action == act_open_folder:
            staged_p = mod.get("staged_path")
            if staged_p and staged_p.exists():
                folder_to_open = staged_p if staged_p.is_dir() else staged_p.parent
                try:
                    subprocess.Popen(["xdg-open", str(folder_to_open)])
                except Exception as e:
                    QMessageBox.warning(self, "Open Folder Error", f"Could not open file manager: {e}")
        elif action == act_open_web:
            matched = find_best_catalog_match_global(mod["name"])
            link = meta.get("link") or (matched.get("link") if matched else None)
            if not link:
                query = urllib.parse.quote(mod["name"])
                link = f"https://sp-mod.com/mods?query={query}"
            QDesktopServices.openUrl(QUrl(link))
        elif act_author_search and action == act_author_search:
            url = resolve_author_profile_url(mod)
            QDesktopServices.openUrl(QUrl(url))
        elif action == act_toggle:
            self.toggle_mod(mod)
        elif action == act_check_upd:
            self.check_installed_mod_updates()
        elif action == act_copy_path:
            staged_p = mod.get("staged_path")
            if staged_p:
                QApplication.clipboard().setText(str(staged_p))
                QMessageBox.information(self, "Copied Path", f"📋 Path copied to clipboard:\n\n{staged_p}")
        elif action == act_delete:
            self.delete_mod(mod)

    def check_installed_mod_updates(self, *args):
        if not hasattr(self, 'all_installed_mods') or not self.all_installed_mods:
            self.load_installed_mods()

        updates = []
        for mod in getattr(self, 'all_installed_mods', []):
            staged_p = mod.get('staged_path')
            meta = load_mod_meta(staged_p) if staged_p else {}
            matched = find_best_catalog_match_global(mod['name'])

            curr_ver = meta.get('version') if meta else '1.0.0'
            latest_ver = matched.get('version') if matched else None

            if matched and latest_ver and is_version_newer(latest_ver, curr_ver):
                updates.append({
                    'mod': mod,
                    'current_ver': curr_ver,
                    'latest_ver': latest_ver,
                    'title': matched.get('title', mod['name']),
                    'download_url': matched.get('download_url', ''),
                    'link': matched.get('link', '')
                })

        if not updates:
            QMessageBox.information(
                self,
                "Up to Date!",
                "✅ <b>All installed mods are up to date!</b><br>No newer versions were found on sp-mod.com."
            )
            return

        upd_list = "\n".join(f"• <b>{html.escape(u['title'])}</b>: v{u['current_ver']} → <b style='color:#a6e3a1;'>v{u['latest_ver']}</b>" for u in updates[:15])
        extra = f"\n...and {len(updates)-15} more" if len(updates) > 15 else ""

        reply = QMessageBox.question(
            self,
            "Mod Updates Available",
            f"🎉 <b>{len(updates)} mod update(s) available</b>:\n\n"
            f"{upd_list}{extra}\n\n"
            f"Would you like to download and install all available updates now?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            update_mods_queue = [
                {
                    'title': u['title'],
                    'download_url': u['download_url'],
                    'link': u['link'],
                    'version': u['latest_ver']
                }
                for u in updates if u['download_url']
            ]
            if update_mods_queue:
                self.start_dependency_queue_download(update_mods_queue, None)

    def update_bulk_actions_bar(self):
        selected_mods = self.get_selected_installed_mods()
        cnt = len(selected_mods)
        if hasattr(self, 'lbl_selected_count'):
            total_pkgs = len(getattr(self, 'all_installed_mods', []))
            total_files = sum(len(m.get("client_items", [])) + len(m.get("server_items", [])) for m in getattr(self, 'all_installed_mods', []))
            if cnt > 0:
                selected_files = sum(len(m.get("client_items", [])) + len(m.get("server_items", [])) for m in selected_mods)
                self.lbl_selected_count.setText(f"<b>{cnt}</b> of <b>{total_pkgs}</b> Mod Packages selected ({selected_files} component files)")
            else:
                self.lbl_selected_count.setText(f"<b>{total_pkgs}</b> Mod Packages installed (<b>{total_files}</b> component files)")
        if hasattr(self, 'btn_bulk_enable'):
            self.btn_bulk_enable.setEnabled(cnt > 0)
            self.btn_bulk_disable.setEnabled(cnt > 0)
            self.btn_bulk_delete.setEnabled(cnt > 0)

    def get_selected_installed_mods(self):
        rows = set(item.row() for item in self.table_mods.selectedItems())
        selected = []
        for r in sorted(list(rows)):
            item = self.table_mods.item(r, 1)
            if item:
                mod_data = item.data(Qt.UserRole)
                if mod_data:
                    selected.append(mod_data)
        return selected

    def select_all_installed_mods(self):
        self.table_mods.selectAll()

    def deselect_all_installed_mods(self):
        self.table_mods.clearSelection()

    def bulk_enable_selected(self):
        selected = self.get_selected_installed_mods()
        if not selected:
            return
        
        enabled_count = 0
        for mod in selected:
            if mod.get("disabled", False):
                client_items = mod.get("client_items", [])
                server_items = mod.get("server_items", [])
                for item, live_link, _ in client_items:
                    if live_link.is_symlink() or live_link.exists():
                        if live_link.is_symlink() or not live_link.is_dir(): live_link.unlink()
                        else: shutil.rmtree(live_link)
                    os.symlink(str(item), str(live_link))
                for item, live_link, _ in server_items:
                    if live_link.is_symlink() or live_link.exists():
                        if live_link.is_symlink() or not live_link.is_dir(): live_link.unlink()
                        else: shutil.rmtree(live_link)
                    os.symlink(str(item), str(live_link))

                enabled_count += 1

        self.load_installed_mods()
        QMessageBox.information(self, "Bulk Enable Complete", f"▶ Enabled <b>{enabled_count}</b> mod package(s)!")

    def bulk_disable_selected(self):
        selected = self.get_selected_installed_mods()
        if not selected:
            return

        disabled_count = 0
        for mod in selected:
            if not mod.get("disabled", False):
                client_items = mod.get("client_items", [])
                server_items = mod.get("server_items", [])
                for _, live_link, _ in client_items:
                    if live_link.is_symlink() or live_link.exists():
                        if live_link.is_symlink() or not live_link.is_dir(): live_link.unlink()
                        else: shutil.rmtree(live_link)
                for _, live_link, _ in server_items:
                    if live_link.is_symlink() or live_link.exists():
                        if live_link.is_symlink() or not live_link.is_dir(): live_link.unlink()
                        else: shutil.rmtree(live_link)

                disabled_count += 1

        self.load_installed_mods()
        QMessageBox.information(self, "Bulk Disable Complete", f"⏸ Disabled <b>{disabled_count}</b> mod package(s)!")

    def bulk_delete_selected(self):
        selected = self.get_selected_installed_mods()
        if not selected:
            return

        names = "\n".join(f"• {m['name']}" for m in selected[:15])
        extra = f"\n...and {len(selected)-15} more" if len(selected) > 15 else ""
        reply = QMessageBox.question(
            self,
            "Delete Selected Mods?",
            f"Are you sure you want to PERMANENTLY delete <b>{len(selected)} selected mod package(s)</b>?\n\n"
            f"{names}{extra}\n\n"
            f"This will delete all staged files and live symlinks.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for mod in selected:
                purge_mod_files_and_symlinks(mod)

            self.load_installed_mods()
            QMessageBox.information(self, "Bulk Delete Complete", f"🗑 Deleted <b>{len(selected)}</b> mod package(s)!")

    def filter_installed_mods(self, text):
        query = text.lower().strip()
        filtered = [m for m in self.all_installed_mods if query in m["name"].lower() or query in m["type"].lower()]
        self.render_installed_mods(filtered)

    def toggle_mod(self, mod):
        try:
            if mod["disabled"]:
                mod_url = None
                matched = next((m for m in self.remote_mods if m["title"].lower() in mod["name"].lower() or mod["name"].lower() in m["title"].lower()), None)
                if matched:
                    mod_url = matched.get("link")

                if mod_url:
                    deps = fetch_mod_dependencies_sync({"link": mod_url})
                    staged_disabled_deps = [d for d in deps if d.get("status") == "STAGED_DISABLED"]
                    if staged_disabled_deps:
                        dep_names = "\n".join(f"• {d['title']}" for d in staged_disabled_deps)
                        reply = QMessageBox.question(
                            self,
                            "Enable Required Dependencies?",
                            f"<b>{mod['name']}</b> requires the following dependency mod(s) which are currently disabled in your Stash:\n\n"
                            f"{dep_names}\n\n"
                            f"Would you like to enable these dependencies as well?",
                            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                        )
                        if reply == QMessageBox.Cancel:
                            return
                        if reply == QMessageBox.Yes:
                            for d in staged_disabled_deps:
                                dep_p = d["path"]
                                is_srv = "server" in str(dep_p).lower()
                                link_p = (SERVER_MODS_DIR if is_srv else CLIENT_MODS_DIR) / dep_p.name
                                if link_p.is_symlink() or link_p.exists():
                                    if link_p.is_symlink() or not link_p.is_dir(): link_p.unlink()
                                    else: shutil.rmtree(link_p)
                                os.symlink(str(dep_p), str(link_p))

                if mod.get("has_client") and mod.get("client_staged") and mod.get("client_live"):
                    cl_live = mod["client_live"]
                    if cl_live.is_symlink() or cl_live.exists():
                        if cl_live.is_symlink() or not cl_live.is_dir(): cl_live.unlink()
                        else: shutil.rmtree(cl_live)
                    os.symlink(str(mod["client_staged"]), str(cl_live))

                if mod.get("has_server") and mod.get("server_staged") and mod.get("server_live"):
                    sv_live = mod["server_live"]
                    if sv_live.is_symlink() or sv_live.exists():
                        if sv_live.is_symlink() or not sv_live.is_dir(): sv_live.unlink()
                        else: shutil.rmtree(sv_live)
                    os.symlink(str(mod["server_staged"]), str(sv_live))

            else:
                if mod.get("has_client") and mod.get("client_live"):
                    cl_live = mod["client_live"]
                    if cl_live.is_symlink() or cl_live.exists():
                        if cl_live.is_symlink() or not cl_live.is_dir(): cl_live.unlink()
                        else: shutil.rmtree(cl_live)

                if mod.get("has_server") and mod.get("server_live"):
                    sv_live = mod["server_live"]
                    if sv_live.is_symlink() or sv_live.exists():
                        if sv_live.is_symlink() or not sv_live.is_dir(): sv_live.unlink()
                        else: shutil.rmtree(sv_live)

            self.load_installed_mods()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to toggle mod: {e}")

    def audit_installed_dependencies(self):
        if not hasattr(self, 'all_installed_mods') or not self.all_installed_mods:
            QMessageBox.information(self, "Audit Dependencies", "No installed mods found to audit.")
            return

        progress = QProgressDialog("🔍 Auditing dependencies for installed mods...", "Cancel", 0, len(self.all_installed_mods), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        issues = []

        for i, mod in enumerate(self.all_installed_mods):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            progress.setLabelText(f"🔍 Auditing ({i+1}/{len(self.all_installed_mods)}): {mod['name']}...")
            QApplication.processEvents()

            matched = next((m for m in self.remote_mods if m["title"].lower() in mod["name"].lower() or mod["name"].lower() in m["title"].lower()), None)
            if matched:
                deps = fetch_mod_dependencies_sync(matched)
                missing = [d for d in deps if d.get("status") == "MISSING"]
                disabled = [d for d in deps if d.get("status") == "STAGED_DISABLED"]
                if missing or disabled:
                    issues.append({
                        "mod_name": mod["name"],
                        "mod_info": matched,
                        "missing": missing,
                        "disabled": disabled
                    })

        progress.setValue(len(self.all_installed_mods))

        if not issues:
            QMessageBox.information(self, "Audit Complete", "✅ All installed mods have their required dependencies installed and enabled!")
            return

        self.show_audit_issues_dialog(issues)

    def show_audit_issues_dialog(self, issues):
        msg = f"<b>Found dependency issues for {len(issues)} installed mod(s):</b><br/><br/>"
        all_missing_to_download = []
        all_disabled_to_enable = []

        for item in issues:
            msg += f"<b>• {item['mod_name']}</b>:<br/>"
            for d in item["disabled"]:
                msg += f"  - <span style='color:#fab387;'>Disabled in Stash:</span> {d['title']}<br/>"
                all_disabled_to_enable.append(d)
            for m in item["missing"]:
                msg += f"  - <span style='color:#f38ba8;'>Missing:</span> {m['title']}<br/>"
                all_missing_to_download.append(m)
            msg += "<br/>"

        msg += "Would you like to automatically enable disabled Stash dependencies and download missing dependencies?"

        reply = QMessageBox.question(
            self,
            "Dependency Audit Results",
            msg,
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            for d in all_disabled_to_enable:
                dep_p = d["path"]
                is_srv = "server" in str(dep_p).lower()
                link_p = (SERVER_MODS_DIR if is_srv else CLIENT_MODS_DIR) / dep_p.name
                if link_p.is_symlink() or link_p.exists():
                    if link_p.is_symlink() or not link_p.is_dir(): link_p.unlink()
                    else: shutil.rmtree(link_p)
                os.symlink(str(dep_p), str(link_p))

            if all_missing_to_download:
                self.start_dependency_queue_download(all_missing_to_download, None)

            self.load_installed_mods()
            QMessageBox.information(self, "Audit Auto-Fix", "✅ Dependency auto-fix process completed!")

    def delete_mod(self, mod):
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to permanently delete '{mod['name']}' from your staged library?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                purge_mod_files_and_symlinks(mod["name"])
                self.load_installed_mods()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete mod: {e}")

    def export_stash_manifest(self):
        if not hasattr(self, 'all_installed_mods') or not self.all_installed_mods:
            QMessageBox.information(self, "Export Stash Manifest", "No installed mods found to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Stash Manifest", str(Path.home() / "stash_manifest.html"), "HTML Files (*.html)"
        )
        if not file_path:
            return

        catalog_mods = self.remote_mods
        if not catalog_mods and CATALOG_CACHE_FILE.exists():
            try:
                with open(CATALOG_CACHE_FILE, "r", encoding="utf-8") as f:
                    catalog_mods = json.load(f)
            except Exception:
                catalog_mods = []

        def find_best_catalog_match(name):
            clean_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', re.sub(r'\.dll$', '', name, flags=re.I))
            target = re.sub(r'[^a-z0-9]', '', clean_name.lower())
            target_stripped = re.sub(r'^[a-z0-9]+[\.\-_]', '', clean_name, flags=re.I)
            target_stripped = re.sub(r'[^a-z0-9]', '', target_stripped.lower())

            for m in catalog_mods:
                m_clean = re.sub(r'[^a-z0-9]', '', m['title'].lower())
                m_slug = re.sub(r'[^a-z0-9]', '', m['link'].split('/')[-1].lower())
                if target in (m_clean, m_slug) or target_stripped in (m_clean, m_slug):
                    return m

            for m in catalog_mods:
                m_clean = re.sub(r'[^a-z0-9]', '', m['title'].lower())
                m_slug = re.sub(r'[^a-z0-9]', '', m['link'].split('/')[-1].lower())
                if len(target_stripped) >= 4 and (target_stripped in m_clean or m_clean in target_stripped or target_stripped in m_slug):
                    return m
            return None

        manifest_mods = []
        for mod in self.all_installed_mods:
            staged_p = mod.get("staged_path")
            meta_data = load_mod_meta(staged_p) if staged_p else None

            if meta_data and meta_data.get("link"):
                manifest_mods.append({
                    "name": mod["name"],
                    "title": meta_data.get("title", mod["name"]),
                    "author": meta_data.get("author", "Community"),
                    "version": meta_data.get("version", "1.0.0"),
                    "type": mod["type"],
                    "image_url": meta_data.get("image_url", ""),
                    "link": meta_data.get("link", ""),
                    "category": meta_data.get("category", "Other"),
                    "description": meta_data.get("description", ""),
                    "enabled": not mod["disabled"]
                })
            else:
                matched = find_best_catalog_match(mod["name"])
                if matched:
                    manifest_mods.append({
                        "name": mod["name"],
                        "title": matched.get("title", mod["name"]),
                        "author": matched.get("creator", "Community"),
                        "version": matched.get("version", "1.0.0"),
                        "type": mod["type"],
                        "image_url": matched.get("image_url", ""),
                        "link": matched.get("link", ""),
                        "category": matched.get("category", "Other"),
                        "description": matched.get("description", ""),
                        "enabled": not mod["disabled"]
                    })
                else:
                    clean_disp = re.sub(r'([a-z])([A-Z])', r'\1 \2', re.sub(r'\.dll$', '', mod['name'], flags=re.I))
                    manifest_mods.append({
                        "name": mod["name"],
                        "title": clean_disp,
                        "author": "Community",
                        "version": "1.0.0",
                        "type": mod["type"],
                        "image_url": "",
                        "link": f"https://sp-mod.com/mods?query={urllib.parse.quote(clean_disp)}",
                        "category": "Other",
                        "description": f"Installed mod package ({mod['name']})",
                        "enabled": not mod["disabled"]
                    })

        manifest = {
            "manifest_version": "1.0",
            "app": "SPT Stash",
            "spt_version": getattr(self, 'installed_spt_ver', 'SPT 4.1.3'),
            "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mods": manifest_mods
        }

        html_out = generate_html_stash_manifest(manifest)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_out)
            QMessageBox.information(self, "Export Successful", f"✅ Stash Manifest successfully saved to:\n{file_path}\n\nYou can open this file in any browser or share it with friends!")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to save manifest: {e}")

    def import_stash_manifest(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Stash Manifest", str(Path.home()), "HTML / Manifest Files (*.html *.json)"
        )
        if not file_path or not Path(file_path).exists():
            return

        try:
            content = Path(file_path).read_text(encoding="utf-8")
            m = re.search(r'<script id=[\"\']stash-manifest-data[\"\'] type=[\"\']application/json[\"\']>\s*(.*?)\s*</script>', content, re.DOTALL)
            if m:
                json_str = m.group(1)
            else:
                json_str = content

            manifest = json.loads(json_str)
            manifest_mods = manifest.get("mods", [])
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to parse Stash Manifest: {e}")
            return

        if not manifest_mods:
            QMessageBox.warning(self, "Import Warning", "No mod definitions found in this manifest.")
            return

        missing_mods = []
        staged_disabled_mods = []

        for m_mod in manifest_mods:
            st, path = check_dep_status(m_mod.get("title") or m_mod.get("name"))
            if st == "MISSING":
                missing_mods.append(m_mod)
            elif st == "STAGED_DISABLED" and m_mod.get("enabled", True):
                staged_disabled_mods.append({"title": m_mod.get("title") or m_mod["name"], "path": path})

        if staged_disabled_mods:
            for d in staged_disabled_mods:
                dep_p = d["path"]
                is_srv = "server" in str(dep_p).lower()
                link_p = (SERVER_MODS_DIR if is_srv else CLIENT_MODS_DIR) / dep_p.name
                if link_p.is_symlink() or link_p.exists():
                    if link_p.is_symlink() or not link_p.is_dir(): link_p.unlink()
                    else: shutil.rmtree(link_p)
                os.symlink(str(dep_p), str(link_p))
            self.load_installed_mods()

        if missing_mods:
            mod_names = "\n".join(f"• {m.get('title') or m['name']}" for m in missing_mods)
            reply = QMessageBox.question(
                self,
                "Auto-Download Missing Manifest Mods?",
                f"<b>Stash Manifest</b> contains <b>{len(missing_mods)} missing mod(s)</b>:\n\n"
                f"{mod_names}\n\n"
                f"Would you like to automatically download and install these missing mods?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.start_dependency_queue_download(missing_mods, None)
                return

    # ------------------ Presets Tab ------------------
    def setup_presets_tab(self):
        layout = QVBoxLayout(self.tab_presets)

        top_controls = QHBoxLayout()

        btn_new_preset = QPushButton("➕ Save Currently Enabled Mods as Preset")
        btn_new_preset.setStyleSheet("""
            QPushButton { background-color: #27392b; color: #a6e3a1; border: 1px solid #36503c; font-weight: bold; }
            QPushButton:hover { background-color: #314a38; border-color: #a6e3a1; }
        """)
        btn_new_preset.clicked.connect(lambda: self.create_preset_from_stash())
        top_controls.addWidget(btn_new_preset)

        btn_import_p = QPushButton("📥 Import Preset File")
        btn_import_p.clicked.connect(lambda: self.import_preset_file())
        top_controls.addWidget(btn_import_p)

        top_controls.addStretch()

        btn_refresh_p = QPushButton("🔄 Refresh Presets")
        btn_refresh_p.clicked.connect(lambda: self.load_presets_list())
        top_controls.addWidget(btn_refresh_p)

        layout.addLayout(top_controls)

        splitter = QSplitter(Qt.Horizontal)

        self.list_presets = QListWidget()
        self.list_presets.setSpacing(4)
        self.list_presets.itemSelectionChanged.connect(self.on_preset_selected)
        splitter.addWidget(self.list_presets)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        self.web_preset_detail = QTextBrowser()
        self.web_preset_detail.setOpenExternalLinks(True)
        self.web_preset_detail.setStyleSheet("background-color: #181825; border: 1px solid #313244; border-radius: 8px; color: #cdd6f4;")
        right_layout.addWidget(self.web_preset_detail)

        bot_p_layout = QHBoxLayout()

        self.btn_apply_preset = QPushButton("▶ Apply Preset to Game")
        self.btn_apply_preset.setFixedHeight(36)
        self.btn_apply_preset.setStyleSheet("""
            QPushButton { background-color: #27392b; color: #a6e3a1; border: 1px solid #36503c; font-size: 13px; font-weight: bold; border-radius: 6px; }
            QPushButton:hover { background-color: #314a38; border-color: #a6e3a1; }
            QPushButton:disabled { background-color: #1e1e2e; color: #585b70; border: 1px solid #313244; }
        """)
        self.btn_apply_preset.clicked.connect(self.apply_selected_preset)
        self.btn_apply_preset.setEnabled(False)
        bot_p_layout.addWidget(self.btn_apply_preset)

        self.btn_export_preset = QPushButton("📤 Export Preset HTML")
        self.btn_export_preset.setFixedHeight(36)
        self.btn_export_preset.setStyleSheet("""
            QPushButton { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; font-size: 13px; font-weight: bold; border-radius: 6px; }
            QPushButton:hover { background-color: #45475a; }
            QPushButton:disabled { background-color: #1e1e2e; color: #585b70; border: 1px solid #313244; }
        """)
        self.btn_export_preset.clicked.connect(self.export_selected_preset)
        self.btn_export_preset.setEnabled(False)
        bot_p_layout.addWidget(self.btn_export_preset)

        self.btn_delete_preset = QPushButton("🗑 Delete Preset")
        self.btn_delete_preset.setFixedHeight(36)
        self.btn_delete_preset.setStyleSheet("""
            QPushButton { background-color: #3a232e; color: #f38ba8; border: 1px solid #542f3e; font-size: 13px; font-weight: bold; border-radius: 6px; }
            QPushButton:hover { background-color: #4a2c3b; border-color: #f38ba8; }
            QPushButton:disabled { background-color: #1e1e2e; color: #585b70; border: 1px solid #313244; }
        """)
        self.btn_delete_preset.clicked.connect(self.delete_selected_preset)
        self.btn_delete_preset.setEnabled(False)
        bot_p_layout.addWidget(self.btn_delete_preset)

        right_layout.addLayout(bot_p_layout)

        splitter.addWidget(right_widget)
        splitter.setSizes([350, 650])
        layout.addWidget(splitter)

        self.load_presets_list()

    def load_presets_list(self):
        self.list_presets.clear()
        self.btn_apply_preset.setEnabled(False)
        self.btn_export_preset.setEnabled(False)
        self.btn_delete_preset.setEnabled(False)
        self.web_preset_detail.setHtml("<h3 style='color:#a6adc8; text-align:center; margin-top:40px;'>Select a Preset on the left to preview or apply</h3>")

        presets = []
        for p in PRESETS_DIR.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data["file_path"] = p
                    presets.append(data)
            except Exception:
                pass

        presets.sort(key=lambda x: x.get("name", ""))

        for pr in presets:
            item = QListWidgetItem()
            mod_cnt = len(pr.get("mods", []))
            item.setText(f"{pr.get('name', 'Preset')}  ({mod_cnt} mods)")
            item.setData(Qt.UserRole, pr)
            self.list_presets.addItem(item)

    def on_preset_selected(self):
        items = self.list_presets.selectedItems()
        if not items:
            self.btn_apply_preset.setEnabled(False)
            self.btn_export_preset.setEnabled(False)
            self.btn_delete_preset.setEnabled(False)
            return

        preset = items[0].data(Qt.UserRole)
        self.current_selected_preset = preset

        self.btn_apply_preset.setEnabled(True)
        self.btn_export_preset.setEnabled(True)
        self.btn_delete_preset.setEnabled(True)

        name = html.escape(preset.get("name", "Preset"))
        desc = html.escape(preset.get("description", "No description provided."))
        ver = html.escape(preset.get("spt_version", getattr(self, 'installed_spt_ver', 'SPT 4.1.3')))
        created = html.escape(preset.get("created_at", ""))
        mods = preset.get("mods", [])

        mods_table = ""
        for m in mods:
            m_name = m.get("name", "")
            m_raw_title = m.get("title") or m_name
            m_author = m.get("author") or m.get("creator", "Community")
            m_ver = html.escape(str(m.get("version", "")))
            m_type_raw = m.get("type", "Mod")
            m_type = html.escape(m_type_raw)
            m_link = m.get("link")

            if not m_link or m_author == "Community":
                matched = find_best_catalog_match_global(m_name)
                if matched:
                    if not m_link and matched.get("link"):
                        m_link = matched.get("link")
                    if m_author == "Community" and matched.get("creator"):
                        m_author = matched.get("creator")

            m_author = html.escape(m_author)

            # Disambiguate title if filename/foldername differs
            if m_name and m_raw_title.lower() != m_name.lower():
                m_title = f"{html.escape(m_raw_title)} <span style='color:#89b4fa; font-size:11px;'>({html.escape(m_name)})</span>"
            else:
                m_title = html.escape(m_raw_title)

            # Check package-aware live status against all_installed_mods
            matched_installed = next((inst for inst in getattr(self, 'all_installed_mods', []) if inst["name"].lower() == m_raw_title.lower() or inst["name"].lower() == m_name.lower()), None)
            if not matched_installed:
                cat_match = find_best_catalog_match_global(m_raw_title) or find_best_catalog_match_global(m_name)
                if cat_match:
                    matched_installed = next((inst for inst in getattr(self, 'all_installed_mods', []) if inst["name"].lower() == cat_match["title"].lower()), None)

            if matched_installed:
                is_enabled = not matched_installed.get("disabled", False)
                is_staged = True
            else:
                is_server = "server" in m_type_raw.lower()
                target_game_dir = SERVER_MODS_DIR if is_server else CLIENT_MODS_DIR
                target_staged_dir = STAGED_SERVER if is_server else STAGED_CLIENT

                is_enabled = (target_game_dir / m_name).exists() or (target_game_dir / m_name).is_symlink()
                is_staged = (target_staged_dir / m_name).exists()

                if not is_enabled and not is_staged:
                    st, _ = check_dep_status(m_raw_title)
                    is_enabled = (st == "ENABLED")
                    is_staged = (st == "STAGED_DISABLED" or is_enabled)

            if is_enabled:
                st_badge = "<span style='color:#a6e3a1; font-weight:bold;'>🟢 Installed & Enabled</span>"
            elif is_staged:
                st_badge = "<span style='color:#fab387; font-weight:bold;'>🟡 Stashed (Disabled)</span>"
            else:
                st_badge = "<span style='color:#f38ba8; font-weight:bold;'>🔴 Missing (Will Auto-Download)</span>"

            link_html = f"<a href='{html.escape(m_link)}' style='color:#89b4fa;'>View Page</a>" if m_link else "Local Package"

            mods_table += f"""
            <tr>
                <td style='padding:6px; border-bottom:1px solid #313244;'><b>{m_title}</b> <span style='color:#a6adc8;'>v{m_ver}</span></td>
                <td style='padding:6px; border-bottom:1px solid #313244; color:#bac2de;'>by {m_author}</td>
                <td style='padding:6px; border-bottom:1px solid #313244;'>{m_type}</td>
                <td style='padding:6px; border-bottom:1px solid #313244;'>{st_badge}</td>
                <td style='padding:6px; border-bottom:1px solid #313244;'>{link_html}</td>
            </tr>
            """

        html_out = f"""
        <div style='padding:12px;'>
            <h2 style='color:#89b4fa; margin:0 0 6px 0;'>{name}</h2>
            <p style='color:#a6adc8; margin:0 0 12px 0;'>Target: <b>{ver}</b> • Total Mods: <b>{len(mods)}</b> • Saved: {created}</p>
            <p style='color:#cdd6f4; background-color:#313244; padding:10px; border-radius:6px; margin-bottom:16px;'>{desc}</p>
            <h3 style='color:#cba6f7; margin-bottom:8px;'>📦 Mods Included in this Preset:</h3>
            <table style='width:100%; border-collapse:collapse; font-size:12px; color:#cdd6f4;'>
                <thead>
                    <tr style='background-color:#313244; color:#cdd6f4; text-align:left;'>
                        <th style='padding:6px;'>Mod Name</th>
                        <th style='padding:6px;'>Author</th>
                        <th style='padding:6px;'>Type</th>
                        <th style='padding:6px;'>Current Status</th>
                        <th style='padding:6px;'>Link</th>
                    </tr>
                </thead>
                <tbody>
                    {mods_table}
                </tbody>
            </table>
        </div>
        """
        self.web_preset_detail.setHtml(html_out)

    def create_preset_from_stash(self, *args):
        if not hasattr(self, 'all_installed_mods') or not self.all_installed_mods:
            self.load_installed_mods()

        enabled_mods = [m for m in getattr(self, 'all_installed_mods', []) if not m.get("disabled", False)]

        if not enabled_mods:
            QMessageBox.warning(self, "No Enabled Mods", "No currently enabled mods were found in your Stash to save.")
            return

        dlg = SavePresetDialog(len(enabled_mods), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        title, desc = dlg.get_data()
        if not title:
            QMessageBox.warning(self, "Invalid Name", "Preset name cannot be empty.")
            return

        manifest_mods = []
        for mod in enabled_mods:
            staged_p = mod.get('staged_path')
            meta_data = load_mod_meta(staged_p) if staged_p else None
            matched = find_best_catalog_match_global(mod['name'])

            m_title = meta_data.get('title') if meta_data else None
            if not m_title and matched: m_title = matched.get('title')
            if not m_title: m_title = mod['name']

            m_author = meta_data.get('author') if meta_data else None
            if (not m_author or m_author == 'Community') and matched: m_author = matched.get('creator')
            if not m_author: m_author = 'Community'

            m_link = meta_data.get('link') if meta_data else None
            if not m_link and matched: m_link = matched.get('link')
            if not m_link: m_link = ''

            m_ver = meta_data.get('version') if meta_data else None
            if not m_ver and matched: m_ver = matched.get('version')
            if not m_ver: m_ver = '1.0.0'

            m_img = meta_data.get('image_url') if meta_data else None
            if not m_img and matched: m_img = matched.get('image_url')
            if not m_img: m_img = ''

            m_cat = meta_data.get('category') if meta_data else None
            if not m_cat and matched: m_cat = matched.get('category')
            if not m_cat: m_cat = 'Other'

            manifest_mods.append({
                'name': mod['name'],
                'title': m_title,
                'author': m_author,
                'version': m_ver,
                'type': mod['type'],
                'image_url': m_img,
                'link': m_link,
                'category': m_cat,
                'description': meta_data.get('description', '') if meta_data else '',
                'enabled': True
            })

        preset_data = {
            'manifest_version': '1.0',
            'app': 'SPT Stash',
            'name': title,
            'description': desc,
            'spt_version': getattr(self, 'installed_spt_ver', 'SPT 4.1.3'),
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'mods': manifest_mods
        }

        safe_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', title.lower())
        out_file = PRESETS_DIR / f"{safe_id}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(preset_data, f, indent=2)

        self.load_presets_list()
        QMessageBox.information(self, "Preset Created", f"✅ Saved preset <b>{html.escape(title)}</b> with <b>{len(manifest_mods)} active mod(s)</b>!")

    def apply_selected_preset(self):
        if not hasattr(self, 'current_selected_preset') or not self.current_selected_preset:
            return

        preset = self.current_selected_preset
        manifest_mods = preset.get("mods", [])
        
        # Build set of desired enabled mod names (case-insensitive)
        desired_enabled_names = set(
            m["name"].lower() for m in manifest_mods if m.get("enabled", True)
        )

        enabled_count = 0
        disabled_count = 0

        # Scan all staged mods in Stash
        staged_dirs = [("client", STAGED_CLIENT, CLIENT_MODS_DIR), ("server", STAGED_SERVER, SERVER_MODS_DIR)]
        
        for m_type, staged_base, game_base in staged_dirs:
            if not staged_base.exists():
                continue
            for staged_item in staged_base.iterdir():
                if staged_item.name.startswith('.'):
                    continue
                
                item_name_lower = staged_item.name.lower()
                game_target = game_base / staged_item.name
                
                should_be_enabled = item_name_lower in desired_enabled_names
                
                if should_be_enabled:
                    if not (game_target.is_symlink() or game_target.exists()):
                        os.symlink(str(staged_item), str(game_target))
                        enabled_count += 1
                else:
                    if game_target.is_symlink() or game_target.exists():
                        if game_target.is_symlink() or not game_target.is_dir(): game_target.unlink()
                        else: shutil.rmtree(game_target)
                        disabled_count += 1

        # Check for any missing catalog mods that are not in Stash
        missing_mods = []
        for m in manifest_mods:
            if m.get("enabled", True):
                m_name = m["name"].lower()
                m_type = m.get("type", "")
                is_server = "server" in m_type.lower()
                target_staged = STAGED_SERVER if is_server else STAGED_CLIENT

                in_stash = (target_staged / m["name"]).exists() or (target_staged.exists() and any(p.name.lower() == m_name for p in target_staged.iterdir()))
                if not in_stash:
                    missing_mods.append(m)

        self.load_installed_mods()
        self.on_preset_selected()

        if missing_mods:
            mod_names = "\n".join(f"• {m.get('title') or m['name']}" for m in missing_mods)
            reply = QMessageBox.question(
                self,
                "Auto-Download Missing Preset Mods?",
                f"Preset <b>{html.escape(preset.get('name', 'Preset'))}</b> includes <b>{len(missing_mods)} missing mod(s)</b>:\n\n"
                f"{mod_names}\n\n"
                f"Would you like to automatically download and install these missing mods now?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.start_dependency_queue_download(missing_mods, None)
                return

        QMessageBox.information(self, "Preset Applied", f"⚡ Preset <b>{html.escape(preset.get('name', 'Preset'))}</b> successfully applied!")

    def export_selected_preset(self):
        if not hasattr(self, 'current_selected_preset') or not self.current_selected_preset:
            return

        preset = self.current_selected_preset
        html_out = generate_html_stash_manifest(preset)

        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', preset.get('name', 'preset').lower())
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Preset HTML Manifest",
            str(Path.home() / f"{clean_name}.html"),
            "HTML Manifest Files (*.html);;JSON Manifest Files (*.json)"
        )
        if not file_path:
            return

        try:
            p = Path(file_path)
            if p.suffix.lower() == ".json":
                p.write_text(json.dumps(preset, indent=2), encoding="utf-8")
            else:
                p.write_text(html_out, encoding="utf-8")
            QMessageBox.information(self, "Export Complete", f"✅ Preset exported to <b>{html.escape(str(p))}</b>")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export preset: {e}")

    def import_preset_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Preset File",
            str(Path.home()),
            "SPT Manifest Files (*.html *.json);;All Files (*)"
        )
        if not file_path:
            return

        try:
            p = Path(file_path)
            content = p.read_text(encoding="utf-8")
            if p.suffix.lower() == ".html":
                m = re.search(r'<script id="stash-manifest-data" type="application/json">\s*(.*?)\s*</script>', content, re.DOTALL)
                if not m:
                    QMessageBox.critical(self, "Import Error", "Could not find embedded manifest data in this HTML file.")
                    return
                preset_data = json.loads(m.group(1))
            else:
                preset_data = json.loads(content)

            preset_name = preset_data.get("name") or preset_data.get("title") or p.stem
            preset_data["name"] = preset_name
            safe_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', preset_name.lower())
            out_file = PRESETS_DIR / f"{safe_id}.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(preset_data, f, indent=2)

            self.load_presets_list()
            QMessageBox.information(self, "Import Complete", f"✅ Imported preset <b>{html.escape(preset_name)}</b> into Presets library!")
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to import preset: {e}")

    def delete_selected_preset(self):
        if not hasattr(self, 'current_selected_preset') or not self.current_selected_preset:
            return

        preset = self.current_selected_preset
        file_p = preset.get("file_path")

        reply = QMessageBox.question(
            self,
            "Delete Preset?",
            f"Are you sure you want to delete preset <b>{html.escape(preset.get('name', 'Preset'))}</b>?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if file_p and Path(file_p).exists():
                Path(file_p).unlink()
            self.load_presets_list()

    # ------------------ Browse Tab (sp-mod.com) ------------------
    def setup_browse_tab(self):
        layout = QVBoxLayout(self.tab_browse)

        filter_layout = QHBoxLayout()
        self.browse_search = QLineEdit()
        self.browse_search.setPlaceholderText("Search online mods...")
        self.browse_search.textChanged.connect(self.filter_remote_mods)
        filter_layout.addWidget(self.browse_search)

        self.combo_category = QComboBox()
        self.combo_category.addItem("All Categories")
        self.combo_category.currentTextChanged.connect(self.filter_remote_mods)
        filter_layout.addWidget(self.combo_category)

        self.combo_sort = QComboBox()
        self.combo_sort.addItems([
            "Sort: Newest",
            "Sort: Recently Updated",
            "Sort: Most Downloaded",
            "Sort: Most Favourited",
            "Sort: Most Endorsed"
        ])
        self.combo_sort.currentTextChanged.connect(self.filter_remote_mods)
        filter_layout.addWidget(self.combo_sort)

        self.installed_spt_ver = detect_installed_spt_version()
        self.chk_installed_version = QCheckBox(f"Filter for Installed ({self.installed_spt_ver})")
        self.chk_installed_version.setStyleSheet("font-weight: bold; color: #a6e3a1;")
        self.chk_installed_version.setChecked(True)
        self.chk_installed_version.toggled.connect(self.filter_remote_mods)
        filter_layout.addWidget(self.chk_installed_version)

        btn_fetch = QPushButton("🌐 Refresh Feed")
        btn_fetch.clicked.connect(lambda: self.fetch_remote_mods(force_refresh=True))
        filter_layout.addWidget(btn_fetch)

        layout.addLayout(filter_layout)

        splitter = QSplitter(Qt.Horizontal)

        self.list_remote = QListWidget()
        self.list_remote.setSpacing(4)
        self.list_remote.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_remote.setItemDelegate(ModItemDelegate(self.list_remote))
        self.list_remote.itemSelectionChanged.connect(self.on_remote_mod_selected)
        splitter.addWidget(self.list_remote)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        self.web_detail = RemoteImageTextBrowser()
        self.web_detail.setOpenExternalLinks(True)
        right_layout.addWidget(self.web_detail)

        bot_btn_layout = QHBoxLayout()

        btn_style_base = "font-size: 13px; font-weight: bold; padding: 6px 16px; border-radius: 6px; height: 32px;"

        self.btn_download_mod = QPushButton("📥 Download && Install Mod")
        self.btn_download_mod.setFixedHeight(36)
        self.btn_download_mod.setStyleSheet("""
            QPushButton { background-color: #27392b; color: #a6e3a1; border: 1px solid #36503c; font-size: 13px; font-weight: bold; border-radius: 6px; }
            QPushButton:hover { background-color: #314a38; border-color: #a6e3a1; }
            QPushButton:disabled { background-color: #1e1e2e; color: #585b70; border: 1px solid #313244; }
        """)
        self.btn_download_mod.clicked.connect(self.start_mod_download)
        self.btn_download_mod.setEnabled(False)
        bot_btn_layout.addWidget(self.btn_download_mod)

        self.btn_open_web = QPushButton("🔗 Open Page on sp-mod.com")
        self.btn_open_web.setFixedHeight(36)
        self.btn_open_web.setStyleSheet(f"background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; {btn_style_base}")
        self.btn_open_web.clicked.connect(self.open_mod_in_browser)
        self.btn_open_web.setEnabled(False)
        bot_btn_layout.addWidget(self.btn_open_web)

        right_layout.addLayout(bot_btn_layout)

        splitter.addWidget(right_widget)
        splitter.setSizes([450, 550])

        layout.addWidget(splitter)

        self.fetch_remote_mods(force_refresh=False)

    def fetch_remote_mods(self, force_refresh=False):
        self.list_remote.clear()
        self.web_detail.setHtml("<h3>Loading catalog...</h3>")
        
        self.rss_thread = RSSFetcherThread(self)
        self.rss_thread.force_refresh = force_refresh
        self.rss_thread.progress.connect(lambda p: self.web_detail.setHtml(f"<h3>{p}</h3>"))
        self.rss_thread.fetched.connect(self.on_remote_mods_fetched)
        self.rss_thread.error.connect(lambda err: self.web_detail.setHtml(f"<h3 style='color:red;'>Error fetching catalog: {err}</h3>"))
        self.rss_thread.start()

    def on_remote_mods_fetched(self, items):
        self.remote_mods = items

        site_categories = [
            "Equipment", "Hideout", "Items", "Locales", "Locations",
            "Models", "Other", "Overhauls", "Quests", "Retextures",
            "Tools", "Traders", "Weapons"
        ]
        present_categories = set(m.get("category", "Other") for m in items)

        self.combo_category.blockSignals(True)
        self.combo_category.clear()
        self.combo_category.addItem("All Categories")
        for c in site_categories:
            if c in present_categories:
                self.combo_category.addItem(c)
        for c in sorted(list(present_categories)):
            if c not in site_categories and c != "All Categories":
                self.combo_category.addItem(c)
        self.combo_category.blockSignals(False)

        self.filter_remote_mods()

    def filter_remote_mods(self):
        query = self.browse_search.text().lower().strip()
        cat = self.combo_category.currentText()
        sort_mode = self.combo_sort.currentText() if hasattr(self, 'combo_sort') else "Sort: Newest"
        only_compatible = self.chk_installed_version.isChecked() if hasattr(self, 'chk_installed_version') else False
        installed_ver = getattr(self, 'installed_spt_ver', 'SPT 4.1.3')

        filtered = []
        for mod in self.remote_mods:
            mod_spt = mod.get("spt_version", "")
            if only_compatible and mod_spt and mod_spt != installed_ver:
                continue
            if cat != "All Categories" and mod["category"] != cat:
                continue
            if query and query not in mod["title"].lower() and query not in mod["creator"].lower():
                continue
            filtered.append(mod)

        # Apply sorting
        if sort_mode == "Sort: Most Downloaded":
            filtered.sort(key=lambda x: x.get("downloads", 0), reverse=True)
        elif sort_mode == "Sort: Most Endorsed" or sort_mode == "Sort: Most Favourited":
            filtered.sort(key=lambda x: x.get("endorsements", 0), reverse=True)

        self.list_remote.clear()
        for mod in filtered:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, mod)
            self.list_remote.addItem(item)

    def render_mod_detail_html(self, mod):
        creator = html.escape(mod.get("creator", "Community"))
        ver = html.escape(str(mod.get("version", "")))
        spt_ver = html.escape(mod.get("spt_version", ""))
        cat = html.escape(mod.get("category", "Other"))
        dl_cnt = mod.get("downloads", 0)
        end_cnt = mod.get("endorsements", 0)

        guid = mod.get("guid", "")
        license_str = mod.get("license", "")
        src_code = mod.get("source_code", "")
        vt_url = mod.get("virustotal", "")
        fika_status = mod.get("fika_status", "Unknown")
        has_ai = mod.get("has_ai", False)

        guid_html = f"<tr><td style='color:#a6adc8; padding:4px 0; width:130px;'><b>GUID:</b></td><td><code style='color:#a6e3a1; font-family:monospace;'>{html.escape(guid)}</code></td></tr>" if guid else ""
        license_html = f"<tr><td style='color:#a6adc8; padding:4px 0;'><b>License:</b></td><td>{html.escape(license_str)}</td></tr>" if license_str else ""
        src_html = f"<tr><td style='color:#a6adc8; padding:4px 0;'><b>Source Code:</b></td><td><a href='{html.escape(src_code)}' style='color:#89b4fa;'>{html.escape(src_code)}</a></td></tr>" if src_code else ""
        vt_html = f"<tr><td style='color:#a6adc8; padding:4px 0;'><b>VirusTotal:</b></td><td><a href='{html.escape(vt_url)}' style='color:#a6e3a1;'>Clean Scan Results</a></td></tr>" if vt_url else ""
        ai_html = f"<tr><td style='color:#a6adc8; padding:4px 0;'><b>AI Content:</b></td><td><span style='color:#cba6f7;'>🤖 Includes AI Content</span></td></tr>" if has_ai else ""

        if "Compatible" in fika_status or fika_status == "Yes":
            fika_badge = "<span style='color:#a6e3a1; font-weight:bold;'>🟢 Fika Compatible Version Available</span>"
        elif "Incompatible" in fika_status or fika_status == "No":
            fika_badge = "<span style='color:#f38ba8; font-weight:bold;'>🔴 Fika Incompatible</span>"
        else:
            fika_badge = "<span style='color:#fab387;'>🟡 Compatibility Unknown</span>"

        stats_html = f"📥 {dl_cnt:,} downloads  •  👍 {end_cnt:,} endorsements" if (dl_cnt or end_cnt) else ""

        card_html = f"""
        <div style='background-color:#181825; border:1px solid #313244; border-radius:12px; padding:16px; margin-bottom:16px;'>
            <h3 style='color:#89b4fa; margin:0 0 12px 0;'>📋 Mod Details & Author Info</h3>
            <table style='width:100%; font-size:13px; color:#cdd6f4; border-collapse:collapse;'>
                <tr><td style='color:#a6adc8; padding:4px 0; width:130px;'><b>Author / Creator:</b></td><td><b style='color:#89b4fa;'>{creator}</b></td></tr>
                <tr><td style='color:#a6adc8; padding:4px 0;'><b>Version:</b></td><td><span style='color:#fab387; font-weight:bold;'>v{ver}</span></td></tr>
                <tr><td style='color:#a6adc8; padding:4px 0;'><b>Target SPT:</b></td><td><span style='color:#a6e3a1; font-weight:bold;'>{spt_ver}</span></td></tr>
                <tr><td style='color:#a6adc8; padding:4px 0;'><b>Category:</b></td><td><span style='background-color:#313244; color:#89dceb; padding:2px 8px; border-radius:4px;'>{cat}</span></td></tr>
                {guid_html}
                {license_html}
                {src_html}
                {vt_html}
                <tr><td style='color:#a6adc8; padding:4px 0;'><b>Fika Status:</b></td><td>{fika_badge}</td></tr>
                {ai_html}
                {"<tr><td style='color:#a6adc8; padding:4px 0;'><b>Stats:</b></td><td>" + stats_html + "</td></tr>" if stats_html else ""}
            </table>
        </div>
        """
        deps = mod.get("dependencies", [])
        dep_html = ""
        if deps:
            dep_html = "<div style='background-color:#181825; border:1px solid #fab387; border-radius:8px; padding:12px; margin-top:14px;'>"
            dep_html += f"<h3 style='color:#fab387; margin:0 0 8px 0;'>🔗 Required Dependencies ({len(deps)}):</h3>"
            for d in deps:
                st = d.get("status")
                if st == "ENABLED" or d.get("installed"):
                    status_text = "<span style='color:#a6e3a1; font-weight:bold;'>(✅ Installed & Enabled)</span>"
                elif st == "STAGED_DISABLED":
                    status_text = "<span style='color:#fab387; font-weight:bold;'>(⚠️ In Stash, Disabled — Auto-enables on Download)</span>"
                else:
                    status_text = "<span style='color:#f38ba8; font-weight:bold;'>(❌ Missing — Auto-installs on Download)</span>"

                dep_html += f"<p style='margin:4px 0;'>• <b>{d['title']}</b> {status_text}</p>"
            dep_html += "</div>"

        return mod.get("description", "") + dep_html + card_html

    def on_remote_mod_selected(self):
        items = self.list_remote.selectedItems()
        if not items:
            self.btn_open_web.setEnabled(False)
            self.btn_download_mod.setEnabled(False)
            return

        mod = items[0].data(Qt.UserRole)
        self.current_selected_remote_mod = mod
        self.btn_open_web.setEnabled(True)
        self.btn_download_mod.setEnabled(True)

        status, _ = check_dep_status(mod.get("title", ""))
        if status == "ENABLED":
            self.btn_download_mod.setText("⏸ Disable Installed Mod")
            self.btn_download_mod.setStyleSheet("""
                QPushButton { background-color: #3a232e; color: #f38ba8; border: 1px solid #542f3e; font-size: 13px; font-weight: bold; border-radius: 6px; }
                QPushButton:hover { background-color: #4a2c3b; border-color: #f38ba8; }
            """)
        elif status == "STAGED_DISABLED":
            self.btn_download_mod.setText("▶ Enable Installed Mod")
            self.btn_download_mod.setStyleSheet("""
                QPushButton { background-color: #27392b; color: #a6e3a1; border: 1px solid #36503c; font-size: 13px; font-weight: bold; border-radius: 6px; }
                QPushButton:hover { background-color: #314a38; border-color: #a6e3a1; }
            """)
        else:
            self.btn_download_mod.setText("📥 Download && Install Mod")
            self.btn_download_mod.setStyleSheet("""
                QPushButton { background-color: #27392b; color: #a6e3a1; border: 1px solid #36503c; font-size: 13px; font-weight: bold; border-radius: 6px; }
                QPushButton:hover { background-color: #314a38; border-color: #a6e3a1; }
            """)

        self.web_detail.setHtml(self.render_mod_detail_html(mod))

        # Fetch dependencies in background thread
        self.dep_thread = DependencyFetcherThread(mod, self)
        self.dep_thread.fetched.connect(self.on_dependencies_fetched)
        self.dep_thread.start()

    def on_dependencies_fetched(self, mod_info, deps):
        if not hasattr(self, 'current_selected_remote_mod') or self.current_selected_remote_mod.get("link") != mod_info.get("link"):
            return

        mod_info["dependencies"] = deps
        self.web_detail.setHtml(self.render_mod_detail_html(mod_info))

    def start_mod_download(self):
        if not hasattr(self, 'current_selected_remote_mod') or not self.current_selected_remote_mod:
            return

        mod = self.current_selected_remote_mod

        # Instant toggle for already installed/staged mods
        mod_status, target_path = check_dep_status(mod.get("title", ""))

        if mod_status == "ENABLED":
            if target_path and (target_path.is_symlink() or target_path.exists()):
                if target_path.is_symlink() or not target_path.is_dir(): target_path.unlink()
                else: shutil.rmtree(target_path)
            self.load_installed_mods()
            self.list_remote.viewport().update()
            self.on_remote_mod_selected()
            QMessageBox.information(self, "Mod Disabled", f"⏸ <b>{mod['title']}</b> is now disabled.")
            return

        if mod_status == "STAGED_DISABLED":
            if target_path:
                is_server = "server" in str(target_path).lower()
                live_dir = SERVER_MODS_DIR if is_server else CLIENT_MODS_DIR
                live_link = live_dir / target_path.name
                if live_link.is_symlink() or live_link.exists():
                    if live_link.is_symlink() or not live_link.is_dir(): live_link.unlink()
                    else: shutil.rmtree(live_link)
                os.symlink(str(target_path), str(live_link))
            self.load_installed_mods()
            self.list_remote.viewport().update()
            self.on_remote_mod_selected()
            QMessageBox.information(self, "Mod Enabled", f"⚡ <b>{mod['title']}</b> is now enabled in your game!")
            return

        if "dependencies" not in mod or mod["dependencies"] is None or not mod["dependencies"]:
            self.btn_download_mod.setEnabled(False)
            self.btn_download_mod.setText("⏳ Checking dependencies...")
            QApplication.processEvents()
            mod["dependencies"] = fetch_mod_dependencies_sync(mod)

        deps = mod.get("dependencies", [])
        staged_disabled_deps = [d for d in deps if d.get("status") == "STAGED_DISABLED"]

        if staged_disabled_deps:
            names = "\n".join(f"• {d['title']}" for d in staged_disabled_deps)
            reply = QMessageBox.question(
                self,
                "Enable Required Dependencies?",
                f"<b>{mod['title']}</b> requires the following dependency mod(s) which are currently disabled in your Stash:\n\n"
                f"{names}\n\n"
                f"Would you like to enable these dependencies as well?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if reply == QMessageBox.Cancel:
                self.btn_download_mod.setEnabled(True)
                self.btn_download_mod.setText("⬇️ Download & Install Mod")
                return
            if reply == QMessageBox.Yes:
                for dep in staged_disabled_deps:
                    staged_path = dep["path"]
                    is_server = "server" in str(staged_path).lower()
                    live_dir = SERVER_MODS_DIR if is_server else CLIENT_MODS_DIR
                    live_link = live_dir / staged_path.name
                    if live_link.is_symlink() or live_link.exists():
                        if live_link.is_symlink() or not live_link.is_dir(): live_link.unlink()
                        else: shutil.rmtree(live_link)
                    os.symlink(str(staged_path), str(live_link))
                    dep["status"] = "ENABLED"
                    dep["installed"] = True
                self.load_installed_mods()

        missing_deps = [d for d in deps if d.get("status") == "MISSING" or (not d.get("installed") and d.get("status") != "ENABLED")]

        if missing_deps:
            dep_names = "\n".join(f"• {d['title']}" for d in missing_deps)
            reply = QMessageBox.question(
                self,
                "Auto-Install Missing Dependencies?",
                f"<b>{mod['title']}</b> requires <b>{len(missing_deps)} missing dependency mod(s)</b>:\n\n"
                f"{dep_names}\n\n"
                f"Would you like to automatically download and install these dependencies first?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if reply == QMessageBox.Cancel:
                self.btn_download_mod.setEnabled(True)
                self.btn_download_mod.setText("⬇️ Download & Install Mod")
                return
            if reply == QMessageBox.Yes:
                self.start_dependency_queue_download(missing_deps, mod)
                return

        self.execute_single_mod_download(mod)

    def execute_single_mod_download(self, mod):
        if mod.get("link"):
            mod["dependencies"] = fetch_mod_dependencies_sync(mod)

        dl_url = mod.get("download_url") or mod.get("link")
        self.btn_download_mod.setEnabled(False)
        self.btn_download_mod.setText("⏳ Downloading...")

        self.downloader_thread = ModDownloaderThread(dl_url, mod["title"])
        self.downloader_thread.progress.connect(lambda p, txt: self.btn_download_mod.setText(f"⏳ {txt}"))
        self.downloader_thread.finished.connect(lambda ok, msg, path: self.on_mod_downloaded(ok, msg, path, mod))
        self.downloader_thread.start()

    def start_dependency_queue_download(self, missing_deps, target_mod):
        self.dep_queue = []
        for dep in missing_deps:
            matched = next((m for m in self.remote_mods if m.get("link") == dep.get("link") or m["title"].lower() == dep["title"].lower()), None)
            if matched:
                self.dep_queue.append(matched)
            else:
                self.dep_queue.append({
                    "title": dep["title"],
                    "link": dep["link"],
                    "download_url": dep["link"].replace('/mod/', '/mod/download/'),
                    "version": "latest",
                    "spt_version": getattr(self, 'installed_spt_ver', 'SPT 4.1.3')
                })

        self.target_mod_after_deps = target_mod
        self.process_next_dependency_in_queue()

    def process_next_dependency_in_queue(self):
        if not hasattr(self, 'dep_queue') or not self.dep_queue:
            if hasattr(self, 'target_mod_after_deps') and self.target_mod_after_deps:
                target = self.target_mod_after_deps
                self.target_mod_after_deps = None
                self.execute_single_mod_download(target)
            return

        dep_mod = self.dep_queue.pop(0)
        dl_url = dep_mod.get("download_url") or dep_mod.get("link")

        self.btn_download_mod.setEnabled(False)
        self.btn_download_mod.setText(f"⏳ Auto-downloading dependency: {dep_mod['title']}...")

        self.dep_downloader = ModDownloaderThread(dl_url, dep_mod["title"])
        self.dep_downloader.progress.connect(lambda p, txt: self.btn_download_mod.setText(f"⏳ {dep_mod['title']}: {txt}"))
        self.dep_downloader.finished.connect(lambda ok, msg, path: self.on_dependency_downloaded(ok, msg, path, dep_mod))
        self.dep_downloader.start()

    def on_dependency_downloaded(self, success, message, archive_path, dep_mod):
        if not success:
            QMessageBox.critical(self, "Dependency Download Error", f"Failed to download dependency '{dep_mod['title']}': {message}")
            self.btn_download_mod.setEnabled(True)
            self.btn_download_mod.setText("⬇️ Download & Install Mod")
            return

        stage_dialog = StageInstallDialog(archive_path, dep_mod, parent=self)
        if stage_dialog.exec() == QDialog.Accepted:
            self.btn_download_mod.setText(f"⏳ Installing dependency: {dep_mod['title']}...")
            self.dep_installer = ModInstallerThread(archive_path, mod_info=dep_mod)
            self.dep_installer.finished.connect(lambda ok, msg: self.on_dependency_installed(ok, msg, archive_path))
            self.dep_installer.start()
        else:
            if archive_path and archive_path.exists():
                try: archive_path.unlink()
                except Exception: pass
            self.btn_download_mod.setEnabled(True)
            self.btn_download_mod.setText("⬇️ Download & Install Mod")
            self.dep_queue = []
            self.target_mod_afterdeps = None

    def on_dependency_installed(self, success, message, archive_path):
        if archive_path and archive_path.exists():
            try: archive_path.unlink()
            except Exception: pass

        if not success:
            QMessageBox.critical(self, "Dependency Installation Error", f"Failed to install dependency: {message}")
            self.btn_download_mod.setEnabled(True)
            self.btn_download_mod.setText("⬇️ Download & Install Mod")
            return

        self.load_installed_mods()
        self.process_next_dependency_in_queue()

    def on_mod_downloaded(self, success, message, archive_path, mod_info):
        self.btn_download_mod.setEnabled(True)
        self.btn_download_mod.setText("⬇️ Download & Install Mod")

        if not success:
            QMessageBox.critical(self, "Download Error", f"Failed to download mod: {message}")
            return

        stage_dialog = StageInstallDialog(archive_path, mod_info, parent=self)
        if stage_dialog.exec() == QDialog.Accepted:
            self.lbl_install_status.setText(f"Installing {mod_info['title']}...")
            self.installer_thread = ModInstallerThread(archive_path, mod_info=mod_info)
            self.installer_thread.finished.connect(self.on_mod_installed)
            self.installer_thread.start()
        else:
            if archive_path and archive_path.exists():
                try: archive_path.unlink()
                except Exception: pass

    def open_mod_in_browser(self):
        if hasattr(self, 'current_selected_remote_mod') and self.current_selected_remote_mod.get("link"):
            QDesktopServices.openUrl(self.current_selected_remote_mod["link"])

    # ------------------ Installer Tab ------------------
    def setup_installer_tab(self):
        layout = QVBoxLayout(self.tab_installer)

        group = QGroupBox("Install Local Mod Archive (.zip / .7z)")
        g_layout = QVBoxLayout(group)

        info_lbl = QLabel(
            "Select any SPT mod archive (.zip or .7z). The installer will automatically "
            "normalize Windows file paths, resolve folder names, and place Client (BepInEx) "
            "and Server (user/mods) components into your SPT directory."
        )
        info_lbl.setWordWrap(True)
        g_layout.addWidget(info_lbl)

        btn_select_file = QPushButton("📁 Choose Mod Archive File...")
        btn_select_file.clicked.connect(self.open_file_installer)
        g_layout.addWidget(btn_select_file)

        self.lbl_install_status = QLabel("")
        self.lbl_install_status.setStyleSheet("font-weight: bold;")
        g_layout.addWidget(self.lbl_install_status)

        layout.addWidget(group)
        layout.addStretch()

    def open_file_installer(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Mod Archive", str(Path.home() / "Downloads"), "Archives (*.zip *.7z)"
        )
        if file_path:
            self.lbl_install_status.setText(f"Installing {Path(file_path).name}...")
            self.installer_thread = ModInstallerThread(file_path)
            self.installer_thread.finished.connect(self.on_mod_installed)
            self.installer_thread.start()

    def on_mod_installed(self, success, message):
        if success:
            QMessageBox.information(self, "Success", message)
            self.lbl_install_status.setText("✅ " + message)
            self.load_installed_mods()
        else:
            QMessageBox.critical(self, "Error", message)
            self.lbl_install_status.setText("❌ " + message)

    # ------------------ Linux Performance Tab ------------------
    def setup_performance_tab(self):
        layout = QVBoxLayout(self.tab_performance)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        cfg = load_config()
        deps = audit_system_dependencies()
        cpu_info = detect_cpu_core_allocation()
        gpu_info = detect_gpu_hardware()

        # Header Title & Hardware Detection Banner
        top_header = QHBoxLayout()
        header_v = QVBoxLayout()
        lbl_title = QLabel("⚡ Linux Performance & Game Launch Tuning")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #89b4fa;")
        lbl_sub = QLabel("All performance optimizations are OFF by default. Enable recommended driver flags for your hardware.")
        lbl_sub.setStyleSheet("color: #a6adc8; font-size: 11px;")
        header_v.addWidget(lbl_title)
        header_v.addWidget(lbl_sub)
        
        lbl_hw_badge = QLabel(f"🎮 <b>GPU:</b> {gpu_info['vendor']} ({gpu_info['name'][:32]})")
        lbl_hw_badge.setStyleSheet("background-color: #313244; color: #a6e3a1; border: 1px solid #45475a; font-size: 11px; font-weight: bold; padding: 6px 12px; border-radius: 6px;")
        
        top_header.addLayout(header_v)
        top_header.addStretch()
        top_header.addWidget(lbl_hw_badge)
        layout.addLayout(top_header)

        grid = QGridLayout()
        grid.setSpacing(10)

        card_style = """
            QGroupBox { font-weight: bold; color: #cdd6f4; border: 1px solid #45475a; border-radius: 8px; margin-top: 4px; padding: 10px; background-color: #1e1e2e; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: %COLOR%; }
        """

        # Card 1: MangoHud (0, 0)
        card_mangohud = QGroupBox("📊 MangoHud Performance Overlay")
        card_mangohud.setStyleSheet(card_style.replace("%COLOR%", "#89b4fa"))
        m_lay = QVBoxLayout(card_mangohud)
        m_lay.setSpacing(6)
        
        m_row = QHBoxLayout()
        self.chk_perf_mangohud = QCheckBox("Enable MangoHud Overlay (MANGOHUD=1)")
        self.chk_perf_mangohud.setChecked(cfg.get("enable_mangohud", False) and deps["mangohud"])
        self.chk_perf_mangohud.setStyleSheet("QCheckBox { color: #cdd6f4; font-weight: bold; font-size: 12px; }")
        
        lbl_m_status = QLabel("<span style='color: #a6e3a1; font-weight: bold;'>🟢 mangohud</span>" if deps["mangohud"] else "<span style='color: #f38ba8; font-weight: bold;'>⚠️ missing</span>")
        m_row.addWidget(self.chk_perf_mangohud)
        m_row.addStretch()
        m_row.addWidget(lbl_m_status)
        m_lay.addLayout(m_row)

        m_help = QLabel("<small style='color: #a6adc8;'>Displays real-time FPS, frametime graphs, CPU/GPU temperatures, and VRAM usage over Tarkov.</small>")
        m_help.setWordWrap(True)
        m_lay.addWidget(m_help)
        m_lay.addStretch()
        grid.addWidget(card_mangohud, 0, 0)

        # Card 2: FSR 4 Upgrade (0, 1)
        card_fsr4 = QGroupBox("⚡ AMD FSR 4 Upscaling Upgrade")
        card_fsr4.setStyleSheet(card_style.replace("%COLOR%", "#a6e3a1"))
        f_lay = QVBoxLayout(card_fsr4)
        f_lay.setSpacing(6)
        self.chk_perf_fsr4 = QCheckBox("Enable Proton FSR 4 Upgrade (PROTON_FSR4_UPGRADE=1)")
        self.chk_perf_fsr4.setChecked(cfg.get("enable_fsr4", False))
        self.chk_perf_fsr4.setStyleSheet("QCheckBox { color: #cdd6f4; font-weight: bold; font-size: 12px; }")
        f_help = QLabel("<small style='color: #a6adc8;'>Upgrades Tarkov's in-game upscaler to FSR 4 using Proton-GE / Valve Proton.</small>")
        f_help.setWordWrap(True)
        f_lay.addWidget(self.chk_perf_fsr4)
        f_lay.addWidget(f_help)
        f_lay.addStretch()
        grid.addWidget(card_fsr4, 0, 1)

        # Card 3: DXVK Async & RADV (1, 0)
        card_dxvk = QGroupBox("🚀 DXVK Async & Shader Caching")
        card_dxvk.setStyleSheet(card_style.replace("%COLOR%", "#f9e2af"))
        d_lay = QVBoxLayout(card_dxvk)
        d_lay.setSpacing(6)
        dxvk_label = "Enable DXVK Async & State Cache (DXVK_ASYNC=1, RADV_PERFTEST=gpl)" if gpu_info["vendor"] == "AMD" else "Enable DXVK Async & State Cache (DXVK_ASYNC=1)"
        self.chk_perf_dxvk = QCheckBox(dxvk_label)
        self.chk_perf_dxvk.setChecked(cfg.get("enable_dxvk_async", False))
        self.chk_perf_dxvk.setStyleSheet("QCheckBox { color: #cdd6f4; font-weight: bold; font-size: 12px; }")
        d_help = QLabel("<small style='color: #a6adc8;'>Compiles graphics shaders asynchronously in background threads to eliminate scope-in and firefight micro-stutters.</small>")
        d_help.setWordWrap(True)
        d_lay.addWidget(self.chk_perf_dxvk)
        d_lay.addWidget(d_help)
        d_lay.addStretch()
        grid.addWidget(card_dxvk, 1, 0)

        # Card 4: CPU Core Isolation (1, 1)
        card_cpu = QGroupBox("🧠 CPU Core Isolation (taskset)")
        card_cpu.setStyleSheet(card_style.replace("%COLOR%", "#cba6f7"))
        c_lay = QVBoxLayout(card_cpu)
        c_lay.setSpacing(6)
        
        self.chk_perf_cpu = QCheckBox("Isolate CPU Cores between Server and Client")
        self.chk_perf_cpu.setChecked(cfg.get("enable_cpu_pinning", False) and deps["taskset"])
        self.chk_perf_cpu.setStyleSheet("QCheckBox { color: #cdd6f4; font-weight: bold; font-size: 12px; }")

        btn_autodetect_cpu = QPushButton("🤖 Auto-Detect")
        btn_autodetect_cpu.setStyleSheet("background-color: #313244; color: #cba6f7; border: 1px solid #45475a; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 4px;")
        btn_autodetect_cpu.clicked.connect(self.auto_detect_cpu_allocation_ui)

        lbl_t_status = QLabel("<span style='color: #a6e3a1; font-weight: bold;'>🟢 taskset</span>" if deps["taskset"] else "<span style='color: #f38ba8; font-weight: bold;'>⚠️ missing</span>")

        top_cpu_row = QHBoxLayout()
        top_cpu_row.addWidget(self.chk_perf_cpu)
        top_cpu_row.addStretch()
        top_cpu_row.addWidget(lbl_t_status)
        top_cpu_row.addSpacing(8)
        top_cpu_row.addWidget(btn_autodetect_cpu)
        c_lay.addLayout(top_cpu_row)

        cores_layout = QHBoxLayout()
        lbl_s_cores = QLabel("Server Cores:")
        self.txt_server_cores = QLineEdit(cfg.get("server_cpu_cores", cpu_info["server_cores"]))
        self.txt_server_cores.setFixedWidth(80)
        lbl_c_cores = QLabel("Client Cores:")
        self.txt_client_cores = QLineEdit(cfg.get("client_cpu_cores", cpu_info["client_cores"]))
        self.txt_client_cores.setFixedWidth(80)
        
        cores_layout.addWidget(lbl_s_cores)
        cores_layout.addWidget(self.txt_server_cores)
        cores_layout.addSpacing(12)
        cores_layout.addWidget(lbl_c_cores)
        cores_layout.addWidget(self.txt_client_cores)
        cores_layout.addStretch()
        
        self.lbl_cpu_detected_info = QLabel(f"<small style='color: #cba6f7;'>CPU: <b>{cpu_info['model_name']}</b> ({cpu_info['threads']}T). Rec: Server ({cpu_info['server_cores']}), Client ({cpu_info['client_cores']}).</small>")
        self.lbl_cpu_detected_info.setWordWrap(True)
        
        c_lay.addLayout(cores_layout)
        c_lay.addWidget(self.lbl_cpu_detected_info)
        c_lay.addStretch()
        grid.addWidget(card_cpu, 1, 1)

        # Card 5: NVIDIA Hardware Optimizations (2, 0)
        card_nvidia = QGroupBox("💚 NVIDIA Hardware Optimizations")
        card_nvidia.setStyleSheet(card_style.replace("%COLOR%", "#76b900"))
        n_lay = QVBoxLayout(card_nvidia)
        n_lay.setSpacing(6)
        self.chk_perf_nvidia = QCheckBox("Enable NVIDIA Drivers (NVAPI, DLSS/Reflex, Threaded Shaders)")
        self.chk_perf_nvidia.setChecked(cfg.get("enable_nvidia_opts", False))
        self.chk_perf_nvidia.setStyleSheet("QCheckBox { color: #cdd6f4; font-weight: bold; font-size: 12px; }")
        if gpu_info["vendor"] != "NVIDIA":
            self.chk_perf_nvidia.setEnabled(False)
            self.chk_perf_nvidia.setToolTip(f"NVIDIA optimizations disabled (Detected GPU: {gpu_info['vendor']})")
            n_help = QLabel("<small style='color: #585b70;'>Requires an NVIDIA GeForce GPU (Detected: AMD/Intel GPU).</small>")
        else:
            n_help = QLabel("<small style='color: #a6adc8;'>Exports PROTON_ENABLE_NVAPI=1, DXVK_ENABLE_NVAPI=1, and __GL_THREADED_OPTIMIZATIONS=1.</small>")
        n_help.setWordWrap(True)
        n_lay.addWidget(self.chk_perf_nvidia)
        n_lay.addWidget(n_help)
        n_lay.addStretch()
        grid.addWidget(card_nvidia, 2, 0)

        # Card 6: Feral GameMode (2, 1)
        card_gamemode = QGroupBox("🎮 Feral GameMode Daemon")
        card_gamemode.setStyleSheet(card_style.replace("%COLOR%", "#f38ba8"))
        g_lay = QVBoxLayout(card_gamemode)
        g_lay.setSpacing(6)
        
        g_row = QHBoxLayout()
        self.chk_perf_gamemode = QCheckBox("Enable GameMode Wrapper (gamemoderun)")
        self.chk_perf_gamemode.setChecked(cfg.get("enable_gamemode", False) and deps["gamemode"])
        self.chk_perf_gamemode.setStyleSheet("QCheckBox { color: #cdd6f4; font-weight: bold; font-size: 12px; }")
        
        lbl_g_status = QLabel("<span style='color: #a6e3a1; font-weight: bold;'>🟢 gamemoded</span>" if deps["gamemode"] else "<span style='color: #f38ba8; font-weight: bold;'>⚠️ missing</span>")
        g_row.addWidget(self.chk_perf_gamemode)
        g_row.addStretch()
        g_row.addWidget(lbl_g_status)
        g_lay.addLayout(g_row)

        g_help = QLabel("<small style='color: #a6adc8;'>Requests max CPU performance governor, disk I/O priority, and disables C-state sleeping during raids.</small>")
        g_help.setWordWrap(True)
        g_lay.addWidget(g_help)
        g_lay.addStretch()
        grid.addWidget(card_gamemode, 2, 1)

        layout.addLayout(grid)
        layout.addStretch()

        # Apply Button
        btn_apply = QPushButton("⚡ Save & Apply to launcher.sh & server.sh")
        btn_apply.setFixedHeight(38)
        btn_apply.setStyleSheet("""
            QPushButton { background-color: #a6e3a1; color: #11111b; font-size: 13px; font-weight: bold; border-radius: 6px; padding: 6px 16px; }
            QPushButton:hover { background-color: #b4befe; color: #11111b; }
        """)
        btn_apply.clicked.connect(self.save_and_apply_performance_settings)
        layout.addWidget(btn_apply)

    def save_and_apply_performance_settings(self):
        cfg = load_config()
        cfg["enable_mangohud"] = self.chk_perf_mangohud.isChecked()
        cfg["enable_fsr4"] = self.chk_perf_fsr4.isChecked()
        cfg["enable_dxvk_async"] = self.chk_perf_dxvk.isChecked()
        cfg["enable_cpu_pinning"] = self.chk_perf_cpu.isChecked()
        cfg["enable_nvidia_opts"] = self.chk_perf_nvidia.isChecked()
        cfg["enable_gamemode"] = self.chk_perf_gamemode.isChecked()
        cfg["server_cpu_cores"] = self.txt_server_cores.text().strip() or "0-7"
        cfg["client_cpu_cores"] = self.txt_client_cores.text().strip() or "8-31"
        save_config(cfg)

        spt_dir = Path(cfg.get("spt_path", str(SPT_ROOT)))
        launcher_sh = Path(cfg.get("launcher_script", str(spt_dir / "launcher.sh")))
        server_sh = Path(cfg.get("server_script", str(spt_dir / "server.sh")))

        # Update launcher.sh
        if launcher_sh.exists():
            try:
                content = launcher_sh.read_text(encoding="utf-8")
                content = re.sub(r'ENABLE_CPU_PINNING=\d', f'ENABLE_CPU_PINNING={1 if cfg["enable_cpu_pinning"] else 0}', content)
                content = re.sub(r'CLIENT_CPU_CORES="[^"]*"', f'CLIENT_CPU_CORES="{cfg["client_cpu_cores"]}"', content)
                content = re.sub(r'ENABLE_DXVK_ASYNC=\d', f'ENABLE_DXVK_ASYNC={1 if cfg["enable_dxvk_async"] else 0}', content)
                content = re.sub(r'ENABLE_FSR4=\d', f'ENABLE_FSR4={1 if cfg["enable_fsr4"] else 0}', content)
                content = re.sub(r'ENABLE_MANGOHUD=\d', f'ENABLE_MANGOHUD={1 if cfg["enable_mangohud"] else 0}', content)
                content = re.sub(r'ENABLE_NVIDIA_OPTS=\d', f'ENABLE_NVIDIA_OPTS={1 if cfg["enable_nvidia_opts"] else 0}', content)
                content = re.sub(r'ENABLE_GAMEMODE=\d', f'ENABLE_GAMEMODE={1 if cfg["enable_gamemode"] else 0}', content)
                launcher_sh.write_text(content, encoding="utf-8")
            except Exception as e:
                print(f"Error updating launcher.sh: {e}")

        # Update server.sh
        if server_sh.exists():
            try:
                content = server_sh.read_text(encoding="utf-8")
                content = re.sub(r'ENABLE_CPU_PINNING=\d', f'ENABLE_CPU_PINNING={1 if cfg["enable_cpu_pinning"] else 0}', content)
                content = re.sub(r'SERVER_CPU_CORES="[^"]*"', f'SERVER_CPU_CORES="{cfg["server_cpu_cores"]}"', content)
                server_sh.write_text(content, encoding="utf-8")
            except Exception as e:
                print(f"Error updating server.sh: {e}")

        QMessageBox.information(self, "⚡ Performance Settings Applied",
                                "Performance tuning options have been saved and applied to launcher.sh and server.sh!")

    def auto_detect_cpu_allocation_ui(self):
        info = detect_cpu_core_allocation()
        self.txt_server_cores.setText(info["server_cores"])
        self.txt_client_cores.setText(info["client_cores"])
        self.lbl_cpu_detected_info.setText(f"<small style='color: #a6e3a1;'>🤖 Auto-Detected: <b>{info['model_name']}</b> ({info['threads']} Threads). Applied Server ({info['server_cores']}), Client ({info['client_cores']}).</small>")
        QMessageBox.information(self, "🤖 CPU Allocation Auto-Detected",
                                f"Detected CPU: {info['model_name']}\nTotal Threads: {info['threads']}\n\nRecommended Server Cores: {info['server_cores']}\nRecommended Client Cores: {info['client_cores']}\n\nValues populated into Settings!")

    # ------------------ Server Controls ------------------
    def check_server_status(self):
        res = subprocess.run(["pgrep", "-f", "SPT.Server"], capture_output=True)
        is_running = (res.returncode == 0)
        if is_running:
            self.status_badge.setText("Server: 🟢 Running (127.0.0.1:6969)")
            self.status_badge.setStyleSheet("padding: 4px 10px; border-radius: 12px; background-color: #a6e3a1; color: #11111b; font-weight: bold;")
            if hasattr(self, 'btn_server_control'):
                self.btn_server_control.setText("⬛ Stop Server")
                self.btn_server_control.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold;")
        else:
            self.status_badge.setText("Server: 🔴 Stopped")
            self.status_badge.setStyleSheet("padding: 4px 10px; border-radius: 12px; background-color: #45475a; color: #cdd6f4; font-weight: bold;")
            if hasattr(self, 'btn_server_control'):
                self.btn_server_control.setText("▶ Start Server")
                self.btn_server_control.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold;")

    def show_missing_script_dialog(self, script_name, target_path):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle(f"⚠️ {script_name} Not Found")
        msg.setStyleSheet("""
            QMessageBox { background-color: #1e1e2e; color: #cdd6f4; }
            QLabel { color: #cdd6f4; min-width: 420px; font-size: 13px; }
            QPushButton { background-color: #313244; border: 1px solid #45475a; color: #cdd6f4; padding: 6px 14px; border-radius: 6px; }
            QPushButton:hover { background-color: #45475a; }
        """)
        msg.setText(
            f"<b>Could not find '{script_name}'</b> at:<br><code>{target_path}</code><br><br>"
            f"Please verify your SPT installation folder in <b>Settings</b>.<br><br>"
            f"<i>Note: Select the directory containing server.sh, launcher.sh, BepInEx, and SPT_Runtime (e.g. <code>~/Games/SPT</code>). Do NOT select your Wine/Proton Tarkov prefix.</i>"
        )
        btn_open_settings = msg.addButton("⚙️ Open Settings", QMessageBox.AcceptRole)
        msg.addButton("Cancel", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() == btn_open_settings:
            self.open_settings_dialog()

    def toggle_server_control(self):
        res = subprocess.run(["pgrep", "-f", "SPT.Server"], capture_output=True)
        if res.returncode == 0:
            subprocess.run(["pkill", "-f", "SPT.Server"])
            self.check_server_status()
        else:
            cfg = load_config()
            server_script = Path(cfg.get("server_script", str(SPT_ROOT / "server.sh")))
            if server_script.exists():
                subprocess.Popen([str(server_script)], cwd=str(server_script.parent))
                QMessageBox.information(self, "SPT Server", f"Starting SPT Server script:\n{server_script.name}")
            else:
                self.show_missing_script_dialog("server.sh", server_script)
            self.check_server_status()

    def launch_spt(self):
        cfg = load_config()
        launcher_script = Path(cfg.get("launcher_script", str(SPT_ROOT / "launcher.sh")))
        if launcher_script.exists():
            subprocess.Popen([str(launcher_script)], cwd=str(launcher_script.parent))
            QMessageBox.information(self, "SPT Launch", f"Launching SPT via:\n{launcher_script.name}")
        else:
            self.show_missing_script_dialog("launcher.sh", launcher_script)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            cfg = load_config()
            global SPT_ROOT, CLIENT_MODS_DIR, SERVER_MODS_DIR, STAGED_DIR, STAGED_CLIENT, STAGED_SERVER
            SPT_ROOT = Path(cfg["spt_path"]).resolve()
            CLIENT_MODS_DIR = SPT_ROOT / "BepInEx" / "plugins"
            SERVER_MODS_DIR = SPT_ROOT / "SPT_Runtime" / "user" / "mods"

            staged_base = Path(cfg["staged_dir"]).resolve()
            STAGED_DIR = staged_base
            STAGED_CLIENT = staged_base / "client"
            STAGED_SERVER = staged_base / "server"
            STAGED_CLIENT.mkdir(parents=True, exist_ok=True)
            STAGED_SERVER.mkdir(parents=True, exist_ok=True)

            self.installed_spt_ver = detect_installed_spt_version()
            self.load_installed_mods()
            QMessageBox.information(self, "Settings Saved", "Settings successfully saved and applied!")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SPTModManagerWindow()
    window.show()
    sys.exit(app.exec())
