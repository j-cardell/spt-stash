#!/usr/bin/env python3
"""SPT Stash — shared HTTPS helper so AppImage/PyInstaller bundles trust public roots."""

import ssl
import urllib.request

import certifi


def https_context():
    """Return an SSL context backed by certifi so bundled binaries trust the same roots."""
    return ssl.create_default_context(cafile=certifi.where())


def urlopen_with_certs(url, timeout=8):
    """Open a URL using the certifi CA bundle; falls back to system defaults on SSL errors."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)", "Referer": "https://sp-mod.com/"}
    )  # files.sp-mod.com returns 403 for images without a sp-mod.com Referer
    try:
        return urllib.request.urlopen(req, context=https_context(), timeout=timeout)
    except ssl.SSLError:
        return urllib.request.urlopen(req, timeout=timeout)
