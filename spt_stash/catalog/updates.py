#!/usr/bin/env python3
"""SPT Stash — check GitHub for a newer SPT Stash release (notify only, never self-replaces)."""

import json
import threading
import urllib.request

from PySide6.QtCore import QObject, Signal

from ..version import __version__, is_version_newer
from .http import https_context

LATEST_RELEASE_API = "https://api.github.com/repos/j-cardell/spt-stash/releases/latest"


def newer_release(payload, current=__version__):
    """Return (tag, url) if the GitHub release payload is newer than `current`, else None."""
    tag = str(payload.get("tag_name") or "")
    if tag and is_version_newer(tag, current):
        return tag, payload.get("html_url") or "https://github.com/j-cardell/spt-stash/releases"
    return None


class AppUpdateChecker(QObject):
    """Ask GitHub for the latest release once; emits found(tag, url) only when it is newer. Fails silently.

    Runs on a daemon thread (not a QThread) so closing the window never has to kill it mid-request.
    """

    found = Signal(str, str)

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            req = urllib.request.Request(
                LATEST_RELEASE_API,
                headers={"User-Agent": "spt-stash", "Accept": "application/vnd.github+json"},
            )
            with urllib.request.urlopen(req, context=https_context(), timeout=8) as resp:
                result = newer_release(json.load(resp))
            if result:
                self.found.emit(*result)
        except Exception:
            pass  # offline / rate limited: an update notice is not worth an error
