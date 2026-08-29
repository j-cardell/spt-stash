#!/usr/bin/env python3
"""SPT Stash — semver helpers."""

import re


def parse_version_tuple(ver_str):
    """Parse 'v1.8.0' / '2.2.3-beta' into an int tuple. Unparseable → (0, 0, 0)."""
    if not ver_str:
        return (0, 0, 0)
    clean = re.sub(r"^[vV]", "", str(ver_str).strip())
    parts = re.findall(r"\d+", clean)
    return tuple(int(p) for p in parts[:4]) if parts else (0, 0, 0)


def is_version_newer(latest_ver, current_ver):
    """True iff latest_ver > current_ver (semver tuple compare)."""
    return parse_version_tuple(latest_ver) > parse_version_tuple(current_ver)
