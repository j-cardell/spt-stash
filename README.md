# 🎒 SPT Stash

> **Native Linux Mod Manager & Performance Suite for Single-Player Tarkov (SPT)**

[![CI & Security Audit](https://github.com/j-cardell/spt-stash/actions/workflows/ci.yml/badge.svg)](https://github.com/j-cardell/spt-stash/actions/workflows/ci.yml)
[![Build & Release AppImage](https://github.com/j-cardell/spt-stash/actions/workflows/appimage.yml/badge.svg)](https://github.com/j-cardell/spt-stash/actions/workflows/appimage.yml)
[![License: MIT](https://img.shields.org/badge/license-MIT-green)](LICENSE)

**SPT Stash** is a high-performance native Linux desktop application designed specifically for Single-Player Tarkov (SPT) on Linux and Steam Deck (SteamOS). It provides **in-tree relative symlink staging**, **official Greed.exe (SVM) integration with Proton selector**, **universal server launching with live IP/port tracking**, **Linux hardware & game launch performance tuning**, **non-blocking animated toast notifications**, and **1-click sp-mod.com Forge catalog browsing & updating**.

---

## ✨ Core Features

- **⚡ In-Tree Relative Symlink Staging**: Enable, disable, or swap client (`BepInEx/plugins`) and server (`user/mods`) mods in milliseconds with zero storage duplication using relative in-tree symlinks (`.staged/`).
- **🗂️ Bulk Mod Actions Bar**: Select, enable, disable, or delete multiple mod packages simultaneously with real-time dynamic selection counters (`X of Y packages, Z component files`).
- **🔄 1-Click Update Checker**: Automatically compares installed versions against the [sp-mod.com (The Forge)](https://sp-mod.com) catalog using Semantic Versioning (`is_version_newer`) with 1-click batch updating.
- **🔍 Deep Dependency Auditor & Auto-Fix**: Automatically scans installed mods for missing or staged-disabled dependencies and provides an interactive 1-click auto-fix dialog.
- **🛠️ Official Greed.exe (SVM) & Proton Selector**: Launch the official [Server Value Modifier (SVM)](https://sp-mod.com/mod/236/server-value-modifier-svm) configurator (`Greed.exe`) under your base game Wine prefix with an interactive Proton runner selector in **⚙️ Settings**.
- **🌐 Universal Server Launcher & Live Badge**: Start and stop the SPT server across any Linux distribution with a 21-terminal discovery matrix, background logging fallback, and real-time status badge parsed directly from `http.json` (e.g. `🟢 Server: Running (127.0.0.1:6969)`).
- **✨ Non-Blocking Animated Toast Notifications**: Smooth opacity fade-in / fade-out pill notifications for server operations, game launches, Greed.exe, and settings saves without blocking UI interaction.
- **⚡ Linux Performance & Tuning Suite**: Dedicated tab for configuring **MangoHud overlays**, **AMD FSR 4 upscaling**, **DXVK Async shader compilation**, **Feral GameMode**, **NVIDIA NVAPI optimizations**, and **CPU core isolation (`taskset`)** with 1-click `🤖 Auto-Detect` and script auto-generation for `launcher.sh` and `server.sh`.
- **🌐 Live Mod Catalog Browser**: Search, filter, and 1-click install mods directly from [sp-mod.com (The Forge)](https://sp-mod.com) with 5 sorting modes, target SPT version filtering, dependency resolution, and `.meta.json` sidecar stamping.
- **🎒 Presets & Loadout Manifests**: Save, load, and export loadout presets as self-contained interactive HTML manifests with embedded JSON data blocks.
- **📦 Multi-File Mod Consolidation**: Bundles dual-component mods (Client + Server, e.g. `UI Fixes`, `SAIN`, `Fika`) into clean single-row packages.
- **🟢 Fika Co-Op Compatibility Badges**: Real-time compatibility tracking and badges (`🟢 Compatible`, `🔴 Incompatible`, `🟡 Unknown`) with background sync.
- **🔗 Direct Author Profiles**: Click any mod author's name to open their official user profile page on `sp-mod.com`.

---

## 🖼️ Application Showcase

### 1. Installed Mods Overview
Manage client (`BepInEx/plugins`) and server (`user/mods`) mods with in-tree relative symlink staging (`.staged/`), interactive column sorting, Fika Co-Op compatibility badges, direct clickable author profile links (`https://sp-mod.com/user/<id>/<author>`), and a full right-click context menu. Use the **Bulk Actions Bar** to enable, disable, or delete multiple mods at once, or run **`🔍 Audit Dependencies`** and **`🔄 Check for Updates`**.

![Installed Mods Overview](docs/screenshots/installed_mods.png)

---

### 2. Presets & Manifest Manager
Create, save, and manage loadout presets with live state auto-syncing. Export interactive, self-contained HTML manifests to share your raid loadouts with friends or import manifests from others.

![Presets & Manifests](docs/screenshots/presets.png)

---

### 3. Live Mod Catalog (sp-mod.com Forge)
Browse, search, and 1-click install mods directly from **sp-mod.com (The Forge)** with disk/memory-cached thumbnails, 5 sorting modes (`Newest`, `Recently Updated`, `Most Downloaded`, `Most Favourited`, `Most Endorsed`), target SPT version filtering, dependency auto-detection, and metadata sidecar stamping.

![Browse sp-mod.com Forge Catalog](docs/screenshots/browse_forge.png)

---

### 4. Local Archive Installer
Drag-and-drop or select any local `.zip` or `.7z` mod archive. Automatically normalizes Windows path separators and places Client/Server components into your staging environment. Automatically handles root-level DLLs (e.g. `Unity.VectorGraphics.dll` for Dynamic Maps) and executables (e.g. `Greed.exe` for SVM).

![Install Local Mod Archive](docs/screenshots/install_archive.png)

---

### 5. Linux Performance & Game Launch Tuning
Enable recommended Linux performance driver flags for your hardware with automatic GPU and CPU detection. Toggle **MangoHud overlays**, **AMD FSR 4 upscaling**, **DXVK Async shader compilation**, **Feral GameMode**, **NVIDIA NVAPI/threaded optimizations**, and **CPU core isolation (`taskset`)** with **`🤖 Auto-Detect`** and 1-click script auto-generation for `launcher.sh` and `server.sh`.

![Linux Performance & Launch Tuning](docs/screenshots/linux_performance.png)

---

## ⚙️ Settings & Path Configuration Guide

Click **⚙️ Settings** at the top right of **SPT Stash** to configure your installation paths:

| Setting | Plain-English Description | Example Path |
| :--- | :--- | :--- |
| **SPT Installation Folder** | Root folder where your Single-Player Tarkov installation lives. Must contain `server.sh`, `launcher.sh`, `BepInEx`, and `SPT_Runtime`. <br>⚠️ *Do **NOT** select your Wine/Proton Tarkov prefix directory.* | `~/Games/SPT` |
| **Mod Staging Stash Directory** | In-tree directory where **SPT Stash** stores uncompressed mod files (`SPT_ROOT/.staged`). Mods stay safely stored here and are symlinked into your game when enabled. | `~/Games/SPT/.staged` |
| **Start Server Script Path** | Path to `server.sh` (or `SPT.Server.exe`) used to launch the local SPT server. | `~/Games/SPT/server.sh` |
| **Launch SPT Script Path** | Path to `launcher.sh` (or `SPT.Launcher.exe`) used to start the launcher and game. | `~/Games/SPT/launcher.sh` |
| **Proton / Compatibility Runner** | Dropdown menu allowing you to choose which Proton/GE-Proton version or System Wine executes Windows tools. | `Auto-Detect (GE-Proton11-6)` |
| **Launch Greed.exe (SVM)** | Button to launch official `Greed.exe` inside your base game installation under your SPT Wine Prefix (`~/Games/SPT-Prefix`). Prompts to auto-download SVM from Forge if missing. | *Action Button* |
| **Create Desktop Shortcut** | Installs system application launcher and desktop shortcut with high-resolution 3D icon. | *Action Button* |

> 💡 **Missing Script Alert**: If `server.sh` or `launcher.sh` are not found when launching, **SPT Stash** displays an alert dialog with a direct **`⚙️ Open Settings`** button to update your paths.

### 🛠️ Official Greed.exe (SVM) Wine & Proton Integration

Rather than requiring a clunky custom tab that risks corrupting SVM config schemas, **SPT Stash** integrates the official [Server Value Modifier (SVM)](https://sp-mod.com/mod/236/server-value-modifier-svm) configurator (`Greed.exe`) natively:

- **Proton Version Selector**: Choose between Auto-Detect (newest GE-Proton), specific installed Proton builds (e.g. `GE-Proton11-6`), or system Wine in **⚙️ Settings**.
- **In-Tree Execution**: Runs directly from your configured SPT root (`~/Games/SPT/Greed.exe`), ensuring 100% native compatibility with all your installed server mods in `user/mods/`.
- **Smart Staging & Auto-Placement**: Automatically detects if `Greed.exe` was extracted into `.staged/`, copies the executable to SPT root, and symlinks `user/mods/ServerValueModifier` properly.
- **Interactive Missing Prompt**: If SVM is not installed, clicking **🛠️ Launch Greed.exe (SVM)** in **⚙️ Settings** prompts to immediately navigate to the **Browse sp-mod.com (Forge)** tab with the search pre-filled for 1-click installation.

### 📁 File Locations & System Data Storage

| Component | System Location | Purpose / Description |
| :--- | :--- | :--- |
| **Config File** | `~/.config/spt-mod-manager/config.json` | Stores configured paths (`spt_path`, `staged_dir`, `server_script`, `launcher_script`, `proton_runner`). |
| **Presets Directory** | `~/.config/spt-mod-manager/presets/` | Stores saved raid loadout preset `.json` files. |
| **Mod Staging Stash** | `<SPT_ROOT>/.staged/` (`client/`, `server/`) | Local in-tree directory where downloaded mod archives are extracted for relative symlinking. |
| **Catalog Cache** | `~/.cache/spt-mod-manager/catalog.json` | Offline cache of sp-mod.com Forge mod catalog metadata. |
| **Image & Icon Cache** | `~/.cache/spt-mod-manager/images/` | Cached mod preview thumbnails and icons. |
| **Downloads Cache** | `~/.cache/spt-mod-manager/downloads/` | Temporary cache for downloaded mod archives before extraction. |

---

## 🚀 Installation & Desktop Shortcut Setup

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
# Clone the repository
git clone https://github.com/j-cardell/spt-stash.git
cd spt-stash

# Install PySide6
pip install PySide6

# Run SPT Stash
python3 spt_mod_manager.py
```

### 📌 1-Click Desktop & Application Launcher Shortcut
To add **SPT Stash** to your system application menu and desktop:

```bash
python3 install_desktop_shortcut.py
```
*(You can also click **📌 Create Desktop Shortcut** anytime inside the **⚙️ Settings** dialog).*

---

## 🧪 Testing & Developer Tooling

SPT Stash includes an automated test runner combining AST verification, a Ruff lint gate, and a headless Qt unit test suite:

```bash
# Run linting and unit test suite
python3 run_tests.py

# Or run Ruff linter directly
ruff check spt_stash spt_mod_manager.py
```

---

## 📄 License
Distributed under the MIT License. See `LICENSE` for more information.

