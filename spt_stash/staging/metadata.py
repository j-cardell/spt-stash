#!/usr/bin/env python3
"""SPT Stash — mod metadata sidecar (.meta.json) read/write."""

import json


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
            "source": meta_dict.get("source", "catalog" if meta_dict.get("link") else "local_archive_unlisted"),
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
            with open(meta_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None
