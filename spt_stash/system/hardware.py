#!/usr/bin/env python3
"""SPT Stash — CPU/GPU/driver detection from Linux sysfs. Zero subprocess for hardware."""

import glob
import os
import re
import shutil
import subprocess
from pathlib import Path

from ..paths import find_spt_root


def detect_cpu_core_allocation():
    threads = os.cpu_count() or 8
    model_name = "Linux CPU"
    try:
        if Path("/proc/cpuinfo").exists():
            with open("/proc/cpuinfo", encoding="utf-8") as f:
                for line in f:
                    if "model name" in line:
                        model_name = line.split(":")[1].strip()
                        break
    except Exception:
        pass

    if threads <= 8:
        s_cores = "0-3"
        c_cores = f"4-{threads - 1}" if threads > 4 else "0-3"
    elif threads <= 12:
        s_cores = "0-3"
        c_cores = f"4-{threads - 1}"
    elif threads <= 16:
        s_cores = "0-3"
        c_cores = f"4-{threads - 1}"
    elif threads <= 24:
        s_cores = "0-5"
        c_cores = f"6-{threads - 1}"
    else:
        s_cores = "0-7"
        c_cores = f"8-{threads - 1}"

    return {
        "model_name": model_name,
        "threads": threads,
        "server_cores": s_cores,
        "client_cores": c_cores,
    }


def audit_system_dependencies():
    return {
        "mangohud": shutil.which("mangohud") is not None or Path("/usr/bin/mangohud").exists(),
        "taskset": shutil.which("taskset") is not None or Path("/usr/bin/taskset").exists(),
        "vulkan": shutil.which("vulkaninfo") is not None or Path("/usr/bin/vulkaninfo").exists(),
        "gamemode": shutil.which("gamemoded") is not None
        or shutil.which("gamemoderun") is not None
        or Path("/usr/bin/gamemoded").exists(),
    }


def detect_gpu_hardware():
    vendor = "UNKNOWN"
    gpu_name = "Unknown Graphics Card"

    vendor_names = {
        "0x1002": ("AMD", "AMD Radeon Graphics"),
        "0x10de": ("NVIDIA", "NVIDIA GeForce GPU"),
        "0x8086": ("INTEL", "Intel Graphics"),
    }

    for vendor_file in sorted(glob.glob("/sys/class/drm/card*/device/vendor")):
        try:
            v_id = Path(vendor_file).read_text(encoding="utf-8").strip().lower()
            if v_id in vendor_names:
                v_info = vendor_names[v_id]
                card_dir = Path(vendor_file).parent
                vram_file = card_dir / "mem_info_vram_total"
                t_mb = 0
                if vram_file.exists():
                    t_mb = int(vram_file.read_text(encoding="utf-8").strip()) / 1024 / 1024

                # Prioritize discrete GPU over integrated
                if t_mb > 2000 or vendor == "UNKNOWN":
                    vendor, base_name = v_info
                    gpu_name = f"{base_name} ({t_mb / 1024:.0f}GB VRAM)" if t_mb > 0 else base_name
        except Exception:
            pass

    return {"vendor": vendor, "name": gpu_name}


def detect_installed_spt_version(spt_root=None):
    """Read SPT version from SPTarkov.Server.Core.dll. Pass spt_root explicitly, or use discovery."""
    root = Path(spt_root) if spt_root else find_spt_root()
    dll_path = root / "SPT_Runtime" / "SPTarkov.Server.Core.dll"
    if dll_path.exists():
        try:
            res = subprocess.run(["strings", str(dll_path)], capture_output=True, text=True)
            matches = re.findall(r"\b(4\.\d+\.\d+)\b", res.stdout)
            if matches:
                return f"SPT {matches[0]}"
        except Exception as e:
            print(f"Error reading SPT version: {e}")
    return "SPT 4.1.3"


def get_available_proton_versions():
    """Discover all installed Proton / Proton-GE versions on the system.
    Returns a list of dicts: [{'label': ..., 'id': ..., 'path': ...}]."""
    search_dirs = [
        Path.home() / ".local" / "share" / "Steam" / "compatibilitytools.d",
        Path.home() / ".steam" / "steam" / "compatibilitytools.d",
        Path.home() / ".steam" / "root" / "compatibilitytools.d",
        Path("/usr/share/steam/compatibilitytools.d"),
    ]

    found = []
    seen_names = set()

    for s_dir in search_dirs:
        if s_dir.exists():
            for p in s_dir.iterdir():
                if p.is_dir() and ((p / "proton").exists() or (p / "compatibilitytool.vdf").exists()):
                    if p.name not in seen_names:
                        seen_names.add(p.name)
                        found.append(p)

    def _proton_sort_key(p):
        digits = tuple(int(x) for x in re.findall(r"\d+", p.name))
        is_ge = 1 if "GE-Proton" in p.name else 0
        return (is_ge, digits)

    found.sort(key=_proton_sort_key, reverse=True)

    results = []
    best_name = found[0].name if found else "GE-Proton11-6"
    results.append({
        "label": f"🤖 Auto-Detect (Recommended: {best_name})",
        "id": "auto",
        "path": str(found[0]) if found else str(Path.home() / ".steam" / "steam" / "compatibilitytools.d" / "GE-Proton11-6"),
    })

    for p in found:
        results.append({
            "label": f"🍷 {p.name}",
            "id": p.name,
            "path": str(p),
        })

    results.append({
        "label": "💻 System Wine (/usr/bin/wine)",
        "id": "wine",
        "path": "wine",
    })

    return results


def find_wine_prefix(spt_root=None):
    """Auto-detect the Wine/Proton prefix directory for the SPT installation."""
    root = Path(spt_root).resolve() if spt_root else find_spt_root().resolve()

    # 1. Sibling and child paths based on spt_root
    candidates = [
        root.parent / f"{root.name}-Prefix",
        root.parent / f"{root.name}_prefix",
        root.parent / "SPT-Prefix",
        root.parent / "spt-prefix",
        root / "prefix",
        root / ".prefix",
        root / "pfx",
        Path.home() / "Games" / "SPT-Prefix",
        Path.home() / "Games" / "spt-prefix",
        Path.home() / ".local" / "share" / "wineprefixes" / "spt",
        Path.home() / ".wine",
    ]

    for pfx in candidates:
        if (pfx / "drive_c").exists():
            return pfx.resolve()

    return Path.home() / "Games" / "SPT-Prefix"


def find_umu_run():
    """Locate umu-run executable or return None."""
    custom_umu = Path.home() / ".local" / "share" / "spt-additions" / "runtime" / "umu-run"
    if custom_umu.exists() and os.access(custom_umu, os.X_OK):
        return custom_umu
    system_umu = shutil.which("umu-run")
    if system_umu:
        return Path(system_umu)
    return None
