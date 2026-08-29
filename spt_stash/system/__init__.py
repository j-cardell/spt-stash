#!/usr/bin/env python3
"""SPT Stash — system subpackage."""

from .hardware import (
    audit_system_dependencies,
    detect_cpu_core_allocation,
    detect_gpu_hardware,
    detect_installed_spt_version,
    find_umu_run,
    find_wine_prefix,
    get_available_proton_versions,
)
from .process import is_server_running, launch_spt_launcher, start_server, stop_server

__all__ = [
    "audit_system_dependencies",
    "detect_cpu_core_allocation",
    "detect_gpu_hardware",
    "detect_installed_spt_version",
    "find_umu_run",
    "find_wine_prefix",
    "get_available_proton_versions",
    "is_server_running",
    "launch_spt_launcher",
    "start_server",
    "stop_server",
]
