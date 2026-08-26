# 🎒 SPT Stash

> **Native Linux Mod Manager for Single-Player Tarkov (SPT)**

[![CI & Security Audit](https://github.com/j-cardell/spt-stash/actions/workflows/ci.yml/badge.svg)](https://github.com/j-cardell/spt-stash/actions/workflows/ci.yml)
[![Build & Release AppImage](https://github.com/j-cardell/spt-stash/actions/workflows/appimage.yml/badge.svg)](https://github.com/j-cardell/spt-stash/actions/workflows/appimage.yml)
[![License: MIT](https://img.shields.org/badge/License-MIT-blue.svg)](LICENSE)

**SPT Stash** is a modern, fast, Catppuccin-themed desktop application built specifically for managing Single-Player Tarkov (SPT) client and server mods on Linux and Steam Deck (SteamOS).

---

## ✨ Features

- **⚡ Zero-Copy Symlink Staging**: Stage and un-stage client (`BepInEx/plugins`) and server (`user/mods`) mods instantly without duplicating storage or modifying game files directly.
- **🌐 Live Mod Catalog Browser**: Search, filter, and download mods directly from [sp-mod.com (The Forge)](https://sp-mod.com) with automatic `.meta.json` sidecar stamping.
- **🎒 Presets & Loadout Manifests**: Save, load, and export loadout presets as self-contained HTML manifests. Live state auto-sync updates preset badges whenever mods are toggled or deleted.
- **📦 Multi-File Mod Consolidation**: Bundles client + server files (e.g. `UI Fixes`, `SAIN`, `Fika`) into clean single-row packages.
- **🟢 Fika Co-Op Compatibility Integration**: Automatically queries and displays Fika multiplayer compatibility badges for all installed mods.
- **🔗 Direct Author Profiles**: Click any mod author's name to open their official user profile page on `sp-mod.com`.
- **🛠 Archive Auto-Extractor**: Install `.zip` or `.7z` archives with automatic Linux path separator normalization.
- **🎮 Server & Launcher Execution**: Direct process control for `server.sh` and `launcher.sh` with live `pgrep` status monitoring.

---

## 🚀 Installation & Usage

### Option 1: Standalone AppImage (Recommended)
Download the latest pre-compiled `SPT_Stash-x86_64.AppImage` from [GitHub Releases](https://github.com/j-cardell/spt-stash/releases):

```bash
chmod +x SPT_Stash-x86_64.AppImage
./SPT_Stash-x86_64.AppImage
```

### Option 2: Run from Source
Requires Python 3.10+ and PySide6:

```bash
# Install PySide6
pip install PySide6

# Run SPT Stash
python3 spt_mod_manager.py
```

---

## 🧪 Testing & Quality Assurance

Run the automated AST linter and unit test suite:

```bash
python3 run_tests.py
```

---

## 📄 License
Distributed under the MIT License. See `LICENSE` for more information.
