#!/usr/bin/env python3
"""SPT Stash — run commands on the host when sandboxed in a Flatpak (via flatpak-spawn --host).

Outside a Flatpak every helper is a thin wrapper around subprocess/shutil, so behaviour is unchanged.
"""

import os
import shlex
import shutil
import subprocess

IN_FLATPAK = os.path.exists("/.flatpak-info")


def host_argv(cmd, cwd=None, env=None):
    """Prefix cmd with flatpak-spawn --host (cwd/env forwarded) when sandboxed; else return it as-is."""
    if not IN_FLATPAK:
        return [str(c) for c in cmd]
    pre = ["flatpak-spawn", "--host"]
    if cwd:
        pre.append(f"--directory={cwd}")
    pre += [f"--env={k}={v}" for k, v in (env or {}).items()]
    return pre + [str(c) for c in cmd]


def run(cmd, **kw):
    """subprocess.run on the host."""
    return subprocess.run(host_argv(cmd), **kw)


def popen(cmd, cwd=None, env=None, **kw):
    """subprocess.Popen on the host. env is a dict of *overrides*, merged over the current environment."""
    if IN_FLATPAK:
        return subprocess.Popen(host_argv(cmd, cwd, env), **kw)
    full = {**os.environ, **(env or {})}
    full.pop("LD_LIBRARY_PATH", None)  # PyInstaller/AppImage pollution must not leak into the game/server
    return subprocess.Popen([str(c) for c in cmd], cwd=cwd, env=full, **kw)


def which(name):
    """Locate an executable on the host's PATH."""
    if not IN_FLATPAK:
        return shutil.which(name)
    res = subprocess.run(host_argv(["sh", "-c", f"command -v {shlex.quote(name)}"]), capture_output=True, text=True)
    return res.stdout.strip() or None
