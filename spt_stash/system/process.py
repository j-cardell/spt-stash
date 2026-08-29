#!/usr/bin/env python3
"""SPT Stash — SPT server process start/stop/status with self-match protection."""

import os
import subprocess
from pathlib import Path


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


def is_server_running():
    return len(_server_pids()) > 0


def stop_server():
    """Graceful terminate of all SPT.Server processes."""
    pids = _server_pids()
    for pid in pids:
        try:
            subprocess.run(["kill", str(pid)], capture_output=True)
        except Exception:
            pass
    return len(pids)


def start_server(server_script, env_overrides=None, log_file=None):
    """Launch the SPT server script in a fresh session.
    Returns the Popen handle or raises."""
    server_script = Path(server_script)
    env = os.environ.copy()
    env.pop("LD_LIBRARY_PATH", None)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.Popen(
        [str(server_script)],
        cwd=str(server_script.parent),
        env=env,
        start_new_session=True,
    )


def launch_spt_launcher(launcher_script, extra_args=None):
    launcher_script = Path(launcher_script)
    cmd = [str(launcher_script)] + (extra_args or [])
    return subprocess.Popen(cmd, cwd=str(launcher_script.parent))
