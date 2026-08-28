#!/usr/bin/env python3
"""
SPT Stash — Desktop Shortcut & Application Launcher Installer
Installs system launcher (.desktop) and desktop shortcut for SPT Stash.
"""

import sys
import os
import shutil
import subprocess
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

    # 1. Install PNG Icon from repo docs if available
    repo_icon = repo_dir / "docs" / "spt_stash_icon.png"
    icon_dst = icons_dir / "spt-stash.png"

    if repo_icon.exists():
        shutil.copy(repo_icon, icon_dst)
        print(f"✅ High-res 3D icon installed to: {icon_dst}")
    else:
        # Fallback SVG string
        icon_svg = icons_dir / "spt-stash.svg"
        icon_svg.write_text("""<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"><rect x="8" y="8" width="240" height="240" rx="48" fill="#1e1e2e"/><path d="M 56 68 L 200 68 L 200 180 L 56 180 Z" fill="#d20f39"/></svg>""", encoding="utf-8")
        icon_dst = icon_svg
        print(f"✅ Icon installed to: {icon_dst}")

    # 2. Desktop Entry Content (Using absolute icon path for instant rendering)
    desktop_content = f"""[Desktop Entry]
Name=SPT Stash
Comment=Native Linux Mod Manager for Single-Player Tarkov (SPT)
Exec={exec_cmd}
Icon={icon_dst}
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

    # 4. Write to Desktop if directory exists & mark trusted
    if desktop_dir.exists():
        desk_file = desktop_dir / "spt-stash.desktop"
        desk_file.write_text(desktop_content, encoding="utf-8")
        desk_file.chmod(0o755)
        try:
            subprocess.run(["gio", "set", str(desk_file), "metadata::trusted", "true"], check=False)
        except Exception:
            pass
        print(f"✅ Desktop shortcut created: {desk_file}")

    # 5. Refresh System Icon Cache
    try:
        subprocess.run(["touch", str(icons_dir)], check=False)
        subprocess.run(["gtk-update-icon-cache", "-f", "-t", str(home / ".local" / "share" / "icons" / "hicolor")], check=False)
    except Exception:
        pass

    print("\n✨ Desktop shortcut installation complete!")
    print("You can now launch 'SPT Stash' directly from your application launcher or desktop!")

if __name__ == "__main__":
    install_desktop_shortcut()
