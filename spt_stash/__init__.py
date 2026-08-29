#!/usr/bin/env python3
"""SPT Stash — public API surface (re-exports for external scripts/tests)."""

from .catalog.dependencies import (
    check_dep_status,
    fetch_mod_dependencies_sync,
    is_dependency_installed,
)
from .catalog.matching import find_best_catalog_match_global, resolve_author_profile_url
from .config import AppConfig, load_config, save_config
from .manifest import generate_html_stash_manifest
from .paths import (
    CACHE_DIR,
    CATALOG_CACHE_FILE,
    CONFIG_DIR,
    CONFIG_FILE,
    DOWNLOADS_CACHE_DIR,
    IMAGE_CACHE_DIR,
    PRESETS_DIR,
    STAGED_CLIENT,
    STAGED_DIR,
    STAGED_SERVER,
    apply_spt_root,
    ensure_dirs,
    find_app_icon,
    find_spt_root,
)
from .staging.links import create_relative_symlink, purge_mod_files_and_symlinks
from .staging.metadata import load_mod_meta, save_mod_meta
from .system.hardware import (
    audit_system_dependencies,
    detect_cpu_core_allocation,
    detect_gpu_hardware,
    detect_installed_spt_version,
)
from .version import is_version_newer, parse_version_tuple

__version__ = "1.2.0"

__all__ = [
    "__version__",
    "AppConfig",
    "apply_spt_root",
    "CACHE_DIR",
    "CATALOG_CACHE_FILE",
    "CONFIG_DIR",
    "CONFIG_FILE",
    "DOWNLOADS_CACHE_DIR",
    "IMAGE_CACHE_DIR",
    "PRESETS_DIR",
    "STAGED_CLIENT",
    "STAGED_DIR",
    "STAGED_SERVER",
    "audit_system_dependencies",
    "check_dep_status",
    "create_relative_symlink",
    "detect_cpu_core_allocation",
    "detect_gpu_hardware",
    "detect_installed_spt_version",
    "ensure_dirs",
    "fetch_mod_dependencies_sync",
    "find_app_icon",
    "find_best_catalog_match_global",
    "find_spt_root",
    "generate_html_stash_manifest",
    "is_dependency_installed",
    "is_version_newer",
    "load_config",
    "load_mod_meta",
    "parse_version_tuple",
    "purge_mod_files_and_symlinks",
    "resolve_author_profile_url",
    "save_config",
    "save_mod_meta",
]
