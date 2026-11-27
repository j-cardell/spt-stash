#!/usr/bin/env python3
"""SPT Stash — SPT server process start/stop/status with self-match protection."""

import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path


def perf_launch_spec(cfg, role):
    """Return (command_prefix, env_overrides) for the Performance-tab settings.

    role is "server" (CPU pinning only) or "client" (the launcher/game). Applied at launch time so we never
    rewrite the user's launch scripts; tools that aren't installed are skipped.
    """
    prefix, env = [], {}
    pin = cfg.get("enable_cpu_pinning") and shutil.which("taskset")
    if role == "server":
        if pin:
            prefix += ["taskset", "-c", str(cfg.get("server_cpu_cores") or "0-7")]
        return prefix, env
    if cfg.get("enable_mangohud") and shutil.which("mangohud"):
        prefix.append("mangohud")
    if pin:
        prefix += ["taskset", "-c", str(cfg.get("client_cpu_cores") or "8-31")]
    if cfg.get("enable_gamemode") and shutil.which("gamemoderun"):
        prefix.append("gamemoderun")
    if cfg.get("enable_dxvk_async"):
        env.update({"DXVK_ASYNC": "1", "RADV_PERFTEST": "gpl"})
    if cfg.get("enable_fsr4"):
        env["PROTON_FSR4_UPGRADE"] = "1"  # what the tab's description promises (Proton-GE)
    if cfg.get("enable_nvidia_opts"):
        env.update({"PROTON_ENABLE_NVAPI": "1", "DXVK_ENABLE_NVAPI": "1", "__GL_THREADED_OPTIMIZATIONS": "1"})
    return prefix, env


def _server_pids():
    """Return list of PIDs for a RUNNING SPT.Server.
    Matches SPT.Server, SPT.Server.Linux, and SPT.Server.exe while excluding own PID."""
    my_pid = os.getpid()
    pids = []
    try:
        res = subprocess.run(["pgrep", "-f", "SPT\\.Server"], capture_output=True, text=True)
        if res.returncode == 0:
            for pid_str in res.stdout.split():
                try:
                    pid = int(pid_str)
                    if pid != my_pid:
                        pids.append(pid)
                except ValueError:
                    pass
    except Exception:
        pass
    return pids


def running_client_apps():
    """Names of SPT client apps (launcher, game) that are still open and connected to the server."""
    found = []
    for label, pattern in (("SPT Launcher", "SPT\\.Launcher"), ("Escape From Tarkov", "EscapeFromTarkov\\.exe")):
        try:
            res = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
        except Exception:
            continue
        if any(int(p) != os.getpid() for p in res.stdout.split()):
            found.append(label)
    return found


def is_server_running():
    return len(_server_pids()) > 0


def stop_server(grace=8):
    """SIGTERM all SPT.Server processes; any still alive after `grace` seconds are SIGKILLed.

    The .NET host can hang in graceful shutdown while the launcher/game keeps websockets open, so the
    follow-up kill runs in a background thread and never blocks the UI. Returns the number signalled.
    """
    pids = _server_pids()
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    def _reap():
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline and _server_pids():
            time.sleep(0.5)
        for pid in _server_pids():
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    if pids:
        threading.Thread(target=_reap, daemon=True).start()
    return len(pids)


def start_server(server_script, env_overrides=None, log_file=None, cmd_prefix=None):
    """Launch the SPT server script in a fresh session.
    Returns the Popen handle or raises."""
    server_script = Path(server_script)
    env = os.environ.copy()
    env.pop("LD_LIBRARY_PATH", None)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.Popen(
        [*(cmd_prefix or []), str(server_script)],
        cwd=str(server_script.parent),
        env=env,
        start_new_session=True,
    )


def launch_spt_launcher(launcher_script, extra_args=None, env_overrides=None, cmd_prefix=None):
    launcher_script = Path(launcher_script)
    cmd = [*(cmd_prefix or []), str(launcher_script)] + (extra_args or [])
    env = {**os.environ, **(env_overrides or {})}
    env.pop("LD_LIBRARY_PATH", None)
    return subprocess.Popen(cmd, cwd=str(launcher_script.parent), env=env)


def log_tail(path, lines=14):
    """Last non-empty lines of a text log ('' if it can't be read)."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join([ln for ln in text.splitlines() if ln.strip()][-lines:])
