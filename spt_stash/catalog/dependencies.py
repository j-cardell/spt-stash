#!/usr/bin/env python3
"""SPT Stash — fetch & parse dependency lists + metadata cards from sp-mod.com mod pages."""

import html
import re
import urllib.request

from ..catalog.matching import (
    find_best_catalog_match_global,  # noqa: F401  (re-exported)
)
from ..paths import STAGED_DIR, find_spt_root


def check_dep_status(dep_title):
    """Return (status, path) where status ∈ {ENABLED, STAGED_DISABLED, MISSING}."""
    spt_root = find_spt_root()
    staged_dir = STAGED_DIR

    clean_title = re.sub(r"(\.dll|\.Server|ServerMod|Server|\.Client|Client)$", "", dep_title, flags=re.I).strip()
    target_alphanumeric = re.sub(r"[^a-z0-9]", "", clean_title.lower())

    # 1. ENABLED = present in active game dirs
    game_dirs = [
        spt_root / "BepInEx" / "plugins",
        spt_root / "SPT_Runtime" / "user" / "mods",
        spt_root / "user" / "mods",
    ]
    for d in game_dirs:
        if d.exists():
            for p in d.iterdir():
                if p.name.startswith("."):
                    continue
                p_clean = re.sub(r"[^a-z0-9]", "", p.name.lower())
                if target_alphanumeric and (target_alphanumeric in p_clean or p_clean in target_alphanumeric):
                    return "ENABLED", p

    # 2. STAGED_DISABLED = in the stash, symlinked out
    staged_dirs = [staged_dir / "client", staged_dir / "server"]
    for d in staged_dirs:
        if d.exists():
            for p in d.iterdir():
                if p.name.startswith("."):
                    continue
                p_clean = re.sub(r"[^a-z0-9]", "", p.name.lower())
                if target_alphanumeric and (target_alphanumeric in p_clean or p_clean in target_alphanumeric):
                    return "STAGED_DISABLED", p

    return "MISSING", None


def is_dependency_installed(dep_title):
    status, _ = check_dep_status(dep_title)
    return status == "ENABLED"


def _enrich_mod_info(mod_info, raw_html):
    """Pull GUID/license/source/virustotal/fika/AI tags off the mod page HTML."""
    if not isinstance(mod_info, dict):
        return
    patterns = [
        ("guid", r"GUID</h3>[\s\S]{1,200}?<span[^>]*font-mono[^>]*>\s*([^\s<]+)", lambda m: m.group(1).strip()),
        ("license", r"License</h3>[\s\S]{1,200}?<a[^>]*>\s*([^<\n]+)", lambda m: html.unescape(m.group(1).strip())),
        ("source_code", r"Source Code</h3>[\s\S]{1,300}?<a[^>]+href=[\"']([^\"']+)[\"']", lambda m: m.group(1).strip()),
        (
            "virustotal",
            r"VirusTotal[^<]*</h3>[\s\S]{1,300}?<a[^>]+href=[\"']([^\"']+)[\"']",
            lambda m: m.group(1).strip(),
        ),
        (
            "fika_status",
            r"(Fika\s+(?:Compatible[^\n<]*|Incompatible|Compatibility[^\n<]*))",
            lambda m: m.group(1).strip(),
        ),
    ]
    for key, pat, fmt in patterns:
        if key not in mod_info:
            m = re.search(pat, raw_html, re.I)
            if m:
                mod_info[key] = fmt(m)
    mod_info.setdefault("has_ai", bool(re.search(r"Includes AI Generated Content", raw_html, re.I)))


def fetch_mod_dependencies_sync(mod_info):
    """Scrape a mod page and return [{"title","link","status","path","installed"}, ...]"""
    deps = []
    seen = set()
    url = mod_info.get("link") if isinstance(mod_info, dict) else str(mod_info)
    if not url:
        return deps

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
        raw_html = urllib.request.urlopen(req, timeout=6).read().decode("utf-8")

        _enrich_mod_info(mod_info, raw_html)

        for m in re.finditer(
            r"<a[^>]+href=[\"'](https://sp-mod\.com/mod/\d+/[^\"']+)[\"'][^>]*>(.*?)</a>",
            raw_html,
            re.DOTALL,
        ):
            link = m.group(1)
            inner = m.group(2)
            if link not in seen and link != url:
                title_m = re.search(
                    r"class=[\"'][^\"']*truncate[^\"']*[\"'][^>]*>\s*(.*?)\s*</p>", inner, re.DOTALL
                ) or re.search(r"alt=[\"']([^\"']+)[\"']", inner)
                if title_m:
                    clean_title = html.unescape(title_m.group(1).strip())
                    seen.add(link)
                    status, path = check_dep_status(clean_title)
                    deps.append(
                        {
                            "title": clean_title,
                            "link": link,
                            "status": status,
                            "path": path,
                            "installed": (status == "ENABLED"),
                        }
                    )
    except Exception as e:
        print(f"Sync dep fetch error for {url}: {e}")
    return deps
