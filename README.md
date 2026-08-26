# 🎒 SPT Stash

> **Native Linux Mod Manager for Single-Player Tarkov (SPT)**

[![CI & Security Audit](https://github.com/j-cardell/spt-stash/actions/workflows/ci.yml/badge.svg)](https://github.com/j-cardell/spt-stash/actions/workflows/ci.yml)
[![Build & Release AppImage](https://github.com/j-cardell/spt-stash/actions/workflows/appimage.yml/badge.svg)](https://github.com/j-cardell/spt-stash/actions/workflows/appimage.yml)
[![License: MIT](https://img.shields.org/badge/License-MIT-blue.svg)](LICENSE)

**SPT Stash** is a modern, fast desktop application built specifically for managing Single-Player Tarkov (SPT) client and server mods on Linux and Steam Deck (SteamOS).

---

## 🖼️ Application Showcase

### 1. Installed Mods Overview
Manage client (`BepInEx/plugins`) and server (`user/mods`) mods with zero-copy symlink staging, interactive column sorting, Fika Co-Op compatibility badges, and direct clickable author profile links (`https://sp-mod.com/user/<id>/<author>`).

![Installed Mods Overview](docs/screenshots/installed_mods.png)

---

### 2. Presets & Manifest Manager
Create, save, and manage loadout presets with live state auto-syncing. Export interactive, self-contained HTML manifests to share your raid loadouts with friends.

![Presets & Manifests](docs/screenshots/presets.png)

---

### 3. Live Mod Catalog (sp-mod.com Forge)
Browse, search, and 1-click install mods directly from **sp-mod.com (The Forge)** with dependency auto-detection and metadata sidecar stamping.

![Browse sp-mod.com Forge Catalog](docs/screenshots/browse_forge.png)

---

### 4. Local Archive Installer
Drag-and-drop or select any local `.zip` or `.7z` mod archive. Automatically normalizes Windows path separators and places Client/Server components into your staging environment.

![Install Local Mod Archive](docs/screenshots/install_archive.png)

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

## ⚙️ Settings & Path Configuration Guide

Click **⚙️ Settings** at the top right of **SPT Stash** to configure your installation paths:

| Setting | Plain-English Description | Example Path |
| :--- | :--- | :--- |
| **SPT Installation Folder** | Select the root folder where your Single-Player Tarkov installation lives. Must contain `server.sh`, `launcher.sh`, `BepInEx`, and `SPT_Runtime`. <br>⚠️ *Do **NOT** select your Wine/Proton Tarkov prefix directory.* | `~/Games/SPT` |
| **Mod Staging Stash Directory** | Local directory where **SPT Stash** downloads and extracts mod files. Mods stay safely stored here and are symlinked into your game when enabled. | `~/.local/share/spt-mod-manager/staged` |
| **Start Server Script Path** | Path to `server.sh` (or `SPT.Server.exe`) used to launch the local SPT server. | `~/Games/SPT/server.sh` |
| **Launch SPT Script Path** | Path to `launcher.sh` (or `SPT.Launcher.exe`) used to start the launcher and game. | `~/Games/SPT/launcher.sh` |

> 💡 **Missing Script Alert**: If `server.sh` or `launcher.sh` are not found when launching, **SPT Stash** displays an alert dialog with a direct **`⚙️ Open Settings`** button to update your paths.

### 📁 File Locations & System Data Storage

| Component | System Location | Purpose / Description |
| :--- | :--- | :--- |
| **Config File** | `~/.config/spt-mod-manager/config.json` | Stores configured paths (`spt_path`, `staged_dir`, `server_script`, `launcher_script`). |
| **Presets Directory** | `~/.config/spt-mod-manager/presets/` | Stores saved raid loadout preset `.json` files. |
| **Mod Staging Stash** | `~/.local/share/spt-mod-manager/staged/` | Directory where downloaded mod archives are unzipped before symlinking. |
| **Catalog Cache** | `~/.cache/spt-mod-manager/catalog.json` | Offline cache of sp-mod.com Forge mod catalog metadata. |

---

## 🚀 Installation & Usage

### Option 1: Standalone AppImage (Recommended)
Download the latest pre-compiled `SPT_Stash-x86_64.AppImage` from [GitHub Releases](https://github.com/j-cardell/spt-stash/releases):

```bash
chmod +x SPT_Stash-x86_64.AppImage
./SPT_Stash-x86_64.AppImage
```

### Option 2: Pre-compiled Standalone Linux Binary (`spt-stash`)
Download the standalone executable `spt-stash` binary from [GitHub Releases](https://github.com/j-cardell/spt-stash/releases) (no AppImage wrapper or Python environment required):

```bash
chmod +x spt-stash
./spt-stash
```

### Option 3: Run from Source
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
