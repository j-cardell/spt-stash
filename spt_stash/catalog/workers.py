#!/usr/bin/env python3
"""SPT Stash — background QThread workers for catalog fetch & dependency scrape."""

import html
import json
import re

from PySide6.QtCore import QThread, Signal

from .. import paths
from .dependencies import fetch_mod_dependencies_sync
from .http import urlopen_with_certs


class RSSFetcherThread(QThread):
    """Pull the full sp-mod.com mod catalog (paginated) into a disk cache."""

    fetched = Signal(list)
    progress = Signal(str)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.force_refresh = False

    def run(self):
        try:
            # Use the disk cache unless a force refresh is requested
            if not self.force_refresh and paths.CATALOG_CACHE_FILE.exists():
                with open(paths.CATALOG_CACHE_FILE, encoding="utf-8") as f:
                    mods = json.load(f)
                self.progress.emit("Catalog loaded from offline cache")
                self.fetched.emit(mods)
                return

            mods = []
            seen = set()

            for page in range(1, 15):
                url = f"https://sp-mod.com/mods?perPage=50&page={page}"
                try:
                    raw_html = urlopen_with_certs(url, timeout=8).read().decode("utf-8")
                except Exception as e:
                    if page == 1:
                        self.error.emit(f"Catalog fetch failed: {e}")
                    break

                blocks = raw_html.split('href="https://sp-mod.com/mod/')[1:]
                if not blocks:
                    break

                for b in blocks:
                    m_link = re.search(r"^(\d+/[a-zA-Z0-9\-_]+)", b)
                    if not m_link:
                        continue
                    full_link = f"https://sp-mod.com/mod/{m_link.group(1)}"
                    if full_link in seen:
                        continue
                    seen.add(full_link)

                    m_title = re.search(r'<span class="group-hover:underline">\s*(.*?)\s*</span>', b, re.DOTALL)
                    title = (
                        html.unescape(m_title.group(1).strip())
                        if m_title
                        else m_link.group(1).split("/")[-1].replace("-", " ").title()
                    )

                    m_ver = re.search(
                        r'<span class="text-nowrap font-light text-gray-400">\s*(.*?)\s*</span>',
                        b,
                        re.DOTALL,
                    )
                    ver = m_ver.group(1).strip() if m_ver else ""

                    m_creator = re.search(r"Created by\s+([^<\n]+)", b)
                    creator = m_creator.group(1).strip() if m_creator else "Community"

                    m_spt = re.search(r"badge-version[^>]*>\s*(SPT[^<\n]+)\s*</p>", b)
                    spt_ver = m_spt.group(1).strip() if m_spt else ""

                    m_desc = re.search(r'<p class="@lg:block hidden text-gray-300">\s*(.*?)\s*</p>', b, re.DOTALL)
                    desc = html.unescape(m_desc.group(1).strip()) if m_desc else ""

                    m_img = re.search(r"<img[^>]+src=[\"'](https://files\.sp-mod\.com/mods/[^\"']+)[\"']", b)
                    img_url = m_img.group(1) if m_img else ""
                    img_html = (
                        f"<div style='margin-bottom:12px;'><img src='{img_url}' "
                        f"style='max-width:240px; border-radius:8px;'/></div>"
                        if img_url
                        else ""
                    )

                    m_dl = re.search(r"title=[\"']([0-9,]+)\s+Downloads[\"']", b, re.I)
                    downloads = int(m_dl.group(1).replace(",", "")) if m_dl else 0

                    m_end = re.search(r"title=[\"']([0-9,]+)\s+Endorsements[\"']", b, re.I)
                    endorsements = int(m_end.group(1).replace(",", "")) if m_end else 0

                    dl_url = (
                        f"https://sp-mod.com/mod/download/{m_link.group(1)}/{ver}"
                        if ver
                        else f"https://sp-mod.com/mod/download/{m_link.group(1)}"
                    )

                    mods.append(
                        {
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
                            "description": (
                                f"{img_html}<h2>{title} <span style='font-size:14px; "
                                f"color:#89b4fa;'>v{ver}</span></h2><p><b>Created by:</b> {creator} "
                                f"| <b>Target:</b> {spt_ver}</p><hr/><p>{desc}</p>"
                                f"<p><a href='{full_link}'>Click here to open mod download page "
                                f"on sp-mod.com</a></p>"
                            ),
                            "date": "",
                        }
                    )

                self.progress.emit(f"Updating online catalog... ({len(mods)} mods found)")
                if len(blocks) < 50:
                    break

            with open(paths.CATALOG_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(mods, f, indent=2)

            self.fetched.emit(mods)
        except Exception as e:
            self.error.emit(str(e))


class DependencyFetcherThread(QThread):
    """Scrape one mod's dependency list off its sp-mod.com page."""

    fetched = Signal(dict, list)

    def __init__(self, mod_info, parent=None):
        super().__init__(parent)
        self.mod_info = mod_info

    def run(self):
        deps = fetch_mod_dependencies_sync(self.mod_info)
        self.fetched.emit(self.mod_info, deps)


class ModDetailFetcherThread(QThread):
    """Fetch and cache the full mod description from its sp-mod.com detail page."""

    fetched = Signal(str, str)  # mod_name, full_description_text
    error = Signal(str)

    def __init__(self, mod_name, parent=None):
        super().__init__(parent)
        self.mod_name = mod_name

    def run(self):
        try:
            from .matching import find_best_catalog_match_global

            matched = find_best_catalog_match_global(self.mod_name)
            if not matched or not matched.get("link"):
                self.fetched.emit(self.mod_name, "")
                return

            slug = matched["link"].rstrip("/").split("/")[-1]
            detail_dir = paths.CACHE_DIR / "mod_details"
            detail_dir.mkdir(parents=True, exist_ok=True)
            cache_file = detail_dir / f"{slug}.json"

            if cache_file.exists():
                data = json.loads(cache_file.read_text())
                self.fetched.emit(self.mod_name, data.get("description", ""))
                return

            with urlopen_with_certs(matched["link"], timeout=15) as resp:
                page = resp.read().decode("utf-8")

            m = re.search(
                r'<meta\s+name="description"\s+content="([^"]+)"', page, re.IGNORECASE
            )
            full = html.unescape(m.group(1)) if m else ""
            full = re.sub(r"^The details for .*? on The Forge\.\s*", "", full)

            cache_file.write_text(
                json.dumps({"description": full, "link": matched["link"]}, indent=2)
            )
            self.fetched.emit(self.mod_name, full)
        except Exception as e:
            self.error.emit(str(e))
