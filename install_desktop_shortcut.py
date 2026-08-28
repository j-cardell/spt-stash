#!/usr/bin/env python3
"""
SPT Stash — Desktop Shortcut & Application Launcher Installer
Installs system launcher (.desktop) and desktop shortcut for SPT Stash.
"""

import sys
import os
import shutil
from pathlib import Path

def install_desktop_shortcut():
    print("=" * 50)
    print(" 🎒 SPT Stash Desktop Shortcut Installer ")
    print("=" * 50)

    repo_dir = Path(__file__).parent.resolve()
    script_path = repo_dir / "spt_mod_manager.py"
    executable = sys.executable

    # Check for standalone binary in dist or system path
    dist_bin = repo_dir / "dist" / "spt-stash"
    exec_cmd = f"\"{dist_bin}\"" if dist_bin.exists() else f"\"{executable}\" \"{script_path}\""

    home = Path.home()
    apps_dir = home / ".local" / "share" / "applications"
    icons_dir = home / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    desktop_dir = home / "Desktop"

    apps_dir.mkdir(parents=True, exist_ok=True)
    icons_dir.mkdir(parents=True, exist_ok=True)

    # 1. Install Icon SVG
    icon_svg_content = """<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 24 24" fill="none" stroke="#89b4fa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
  <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
  <line x1="12" y1="22.08" x2="12" y2="12"></line>
</svg>"""

    icon_path = icons_dir / "spt-stash.svg"
    icon_path.write_text(icon_svg_content, encoding="utf-8")
    print(f"✅ Icon installed to: {icon_path}")

    # 2. Desktop Entry Content
    desktop_content = f"""[Desktop Entry]
Name=SPT Stash
Comment=Native Linux Mod Manager for Single-Player Tarkov (SPT)
Exec={exec_cmd}
Icon=spt-stash
Terminal=false
Type=Application
Categories=Game;Utility;
Keywords=SPT;Tarkov;ModManager;Linux;
"""

    # 3. Write to Application Menu
    app_file = apps_dir / "spt-stash.desktop"
    app_file.write_text(desktop_content, encoding="utf-8")
    app_file.chmod(0o755)
    print(f"✅ Application menu launcher installed: {app_file}")

    # 4. Write to Desktop if directory exists
    if desktop_dir.exists():
        desk_file = desktop_dir / "spt-stash.desktop"
        desk_file.write_text(desktop_content, encoding="utf-8")
        desk_file.chmod(0o755)
        print(f"✅ Desktop shortcut created: {desk_file}")

    print("\n✨ Desktop shortcut installation complete!")
    print("You can now launch 'SPT Stash' directly from your application launcher or desktop!")

if __name__ == "__main__":
    install_desktop_shortcut()
