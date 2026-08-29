#!/usr/bin/env python3
"""SPT Stash — catalog matching & author profile resolution (offline, reads disk cache)."""

import json
import re
import urllib.parse
import urllib.request

from ..paths import CATALOG_CACHE_FILE
from ..staging.metadata import save_mod_meta
from .aliases import ALIASES


def find_best_catalog_match_global(name):
    catalog_mods = []
    if CATALOG_CACHE_FILE.exists():
        try:
            with open(CATALOG_CACHE_FILE, encoding="utf-8") as f:
                catalog_mods = json.load(f)
        except Exception:
            catalog_mods = []
    if not catalog_mods:
        return None

    name_clean = re.sub(r"[^a-z0-9]", "", name.lower())
    for alias_k, alias_v in ALIASES.items():
        if alias_k in name_clean:
            for m in catalog_mods:
                if alias_v in m.get("link", "").lower() or alias_v in re.sub(
                    r"[^a-z0-9]", "-", m.get("title", "").lower()
                ):
                    return m

    clean_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", re.sub(r"\.dll$", "", name, flags=re.I))
    target = re.sub(r"[^a-z0-9]", "", clean_name.lower())
    target_stripped = re.sub(r"^[a-z0-9]+[\.\-_]", "", clean_name, flags=re.I)
    target_stripped = re.sub(r"[^a-z0-9]", "", target_stripped.lower())

    for m in catalog_mods:
        m_clean = re.sub(r"[^a-z0-9]", "", m["title"].lower())
        m_slug = re.sub(r"[^a-z0-9]", "", m["link"].split("/")[-1].lower())
        if target in (m_clean, m_slug) or target_stripped in (m_clean, m_slug):
            return m

    for m in catalog_mods:
        m_clean = re.sub(r"[^a-z0-9]", "", m["title"].lower())
        m_slug = re.sub(r"[^a-z0-9]", "", m["link"].split("/")[-1].lower())
        if len(target_stripped) >= 4 and (
            target_stripped in m_clean or m_clean in target_stripped or target_stripped in m_slug
        ):
            return m

    return None


def resolve_author_profile_url(mod_dict):
    from ..staging.metadata import load_mod_meta

    staged_p = mod_dict.get("staged_path")
    meta = (load_mod_meta(staged_p) or {}) if staged_p else {}
    if meta.get("author_link"):
        return meta.get("author_link")

    matched = find_best_catalog_match_global(mod_dict["name"])
    mod_url = meta.get("link") or (matched.get("link") if matched else None)

    if mod_url:
        try:
            req = urllib.request.Request(mod_url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
            raw_html = urllib.request.urlopen(req, timeout=6).read().decode("utf-8")
            user_links = re.findall(
                r"href=[\'\"](https?://sp-mod\.com/user/\d+/[^\'\"]+|/user/\d+/[^\'\"]+)[\'\"]",
                raw_html,
            )
            if user_links:
                profile_url = user_links[0]
                if profile_url.startswith("/"):
                    profile_url = f"https://sp-mod.com{profile_url}"

                meta["author_link"] = profile_url
                if mod_dict.get("client_staged"):
                    save_mod_meta(mod_dict["client_staged"], meta)
                if mod_dict.get("server_staged"):
                    save_mod_meta(mod_dict["server_staged"], meta)
                return profile_url
        except Exception:
            pass

    author_str = meta.get("author") or (matched.get("creator") if matched else "Community")
    return f"https://sp-mod.com/mods?query={urllib.parse.quote(author_str)}"
