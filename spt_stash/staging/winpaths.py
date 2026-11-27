#!/usr/bin/env python3
"""SPT Stash — Linux compatibility for mods that hard-code Windows path separators.

Some server mods ask for 'database\\items.json'. On Linux that is a single file name containing a
backslash, so the mod can't find its own files. When the server's crash log shows exactly that, we add
backslash-named symlinks next to the real files. We never edit the mod's files.
"""

import os
import re
from pathlib import Path

# .NET: "Could not find file '/x/Mod/database\items.json'." (rich may hard-wrap the path across lines)
_MISSING = re.compile(r"Could not find (?:file|a part of the path)\s*'([^']+)'", re.S)


def find_backslash_failures(log_text):
    """Return [(mod_dir, relative_path)] for missing files whose backslash-path exists with real folders."""
    found = []
    for raw in _MISSING.findall(log_text):
        for path in (raw.replace("\n", ""), raw.replace("\n", " ")):  # wrapped at a space or mid-word
            parent, _, name = path.rpartition("/")
            if "\\" not in name:
                continue
            rest = name.replace("\\", "/")
            if (Path(parent) / rest).is_file() and (Path(parent), rest) not in found:
                found.append((Path(parent), rest))
                break
    return found


def create_backslash_aliases(mod_dir, rest):
    """Alias every file under the top folder of `rest` as 'a\\b\\c' → 'a/b/c'. Returns how many were added."""
    mod_dir = Path(mod_dir)
    top = mod_dir / rest.split("/")[0]
    made = 0
    for real in [top] if top.is_file() else sorted(p for p in top.rglob("*") if p.is_file()):
        rel = real.relative_to(mod_dir).as_posix()
        alias = mod_dir / rel.replace("/", "\\")
        if "/" not in rel or alias.exists() or alias.is_symlink():
            continue
        os.symlink(rel, alias)  # relative to the folder the alias lives in (mod_dir)
        made += 1
    return made
