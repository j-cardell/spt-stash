#!/usr/bin/env python3
"""SPT Stash — background QThread workers for catalog fetch & dependency scrape."""

import html
import json
import re
import urllib.request

from PySide6.QtCore import QThread, Signal

from ..paths import CATALOG_CACHE_FILE
from .dependencies import fetch_mod_dependencies_sync


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
            if not self.force_refresh and CATALOG_CACHE_FILE.exists():
                with open(CATALOG_CACHE_FILE, encoding="utf-8") as f:
                    mods = json.load(f)
                self.progress.emit(
                    f"Loaded {len(mods)} mods from offline disk cache (0 network requests made). "
                    "Click 'Refresh sp-mod.com Feed' to check for online updates."
                )
                self.fetched.emit(mods)
                return

            mods = []
            seen = set()

            for page in range(1, 15):
                url = f"https://sp-mod.com/mods?perPage=50&page={page}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
                try:
                    raw_html = urllib.request.urlopen(req, timeout=8).read().decode("utf-8")
                except Exception:
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

            with open(CATALOG_CACHE_FILE, "w", encoding="utf-8") as f:
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
