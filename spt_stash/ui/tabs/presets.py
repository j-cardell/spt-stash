#!/usr/bin/env python3
"""SPT Stash — Presets & Manifests tab."""

import html
import json
import os
import re
import shutil
import time
import urllib.parse
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...catalog.dependencies import check_dep_status
from ...catalog.matching import find_best_catalog_match_global
from ...manifest import generate_html_stash_manifest
from ...paths import (
    CATALOG_CACHE_FILE,
    CLIENT_MODS_DIR,
    PRESETS_DIR,
    SERVER_MODS_DIR,
    STAGED_CLIENT,
    STAGED_SERVER,
)
from ...staging.metadata import load_mod_meta
from ..dialogs import SavePresetDialog


def setup_presets_tab(self):
    layout = QVBoxLayout(self.tab_presets)

    top_controls = QHBoxLayout()

    btn_new_preset = QPushButton("➕ Save Currently Enabled Mods as Preset")
    btn_new_preset.setStyleSheet("""
        QPushButton { background-color: #27392b; color: #a6e3a1; border: 1px solid #36503c; font-weight: bold; }
        QPushButton:hover { background-color: #314a38; border-color: #a6e3a1; }
    """)
    btn_new_preset.clicked.connect(lambda: self.create_preset_from_stash())
    top_controls.addWidget(btn_new_preset)

    btn_import_p = QPushButton("📥 Import Preset File")
    btn_import_p.clicked.connect(lambda: self.import_preset_file())
    top_controls.addWidget(btn_import_p)

    top_controls.addStretch()

    btn_refresh_p = QPushButton("🔄 Refresh Presets")
    btn_refresh_p.clicked.connect(lambda: self.load_presets_list())
    top_controls.addWidget(btn_refresh_p)

    layout.addLayout(top_controls)

    splitter = QSplitter(Qt.Horizontal)

    self.list_presets = QListWidget()
    self.list_presets.setSpacing(4)
    self.list_presets.itemSelectionChanged.connect(self.on_preset_selected)
    splitter.addWidget(self.list_presets)

    right_widget = QWidget()
    right_layout = QVBoxLayout(right_widget)

    self.web_preset_detail = QTextBrowser()
    self.web_preset_detail.setOpenExternalLinks(True)
    self.web_preset_detail.setStyleSheet(
        "background-color: #181825; border: 1px solid #313244; border-radius: 8px; color: #cdd6f4;"
    )
    right_layout.addWidget(self.web_preset_detail)

    bot_p_layout = QHBoxLayout()

    self.btn_apply_preset = QPushButton("▶ Apply Preset to Game")
    self.btn_apply_preset.setFixedHeight(36)
    self.btn_apply_preset.setStyleSheet("""
        QPushButton { background-color: #27392b; color: #a6e3a1; border: 1px solid #36503c; font-size: 13px; font-weight: bold; border-radius: 6px; }
        QPushButton:hover { background-color: #314a38; border-color: #a6e3a1; }
        QPushButton:disabled { background-color: #1e1e2e; color: #585b70; border: 1px solid #313244; }
    """)
    self.btn_apply_preset.clicked.connect(self.apply_selected_preset)
    self.btn_apply_preset.setEnabled(False)
    bot_p_layout.addWidget(self.btn_apply_preset)

    self.btn_export_preset = QPushButton("📤 Export Preset HTML")
    self.btn_export_preset.setFixedHeight(36)
    self.btn_export_preset.setStyleSheet("""
        QPushButton { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; font-size: 13px; font-weight: bold; border-radius: 6px; }
        QPushButton:hover { background-color: #45475a; }
        QPushButton:disabled { background-color: #1e1e2e; color: #585b70; border: 1px solid #313244; }
    """)
    self.btn_export_preset.clicked.connect(self.export_selected_preset)
    self.btn_export_preset.setEnabled(False)
    bot_p_layout.addWidget(self.btn_export_preset)

    self.btn_delete_preset = QPushButton("🗑 Delete Preset")
    self.btn_delete_preset.setFixedHeight(36)
    self.btn_delete_preset.setStyleSheet("""
        QPushButton { background-color: #3a232e; color: #f38ba8; border: 1px solid #542f3e; font-size: 13px; font-weight: bold; border-radius: 6px; }
        QPushButton:hover { background-color: #4a2c3b; border-color: #f38ba8; }
        QPushButton:disabled { background-color: #1e1e2e; color: #585b70; border: 1px solid #313244; }
    """)
    self.btn_delete_preset.clicked.connect(self.delete_selected_preset)
    self.btn_delete_preset.setEnabled(False)
    bot_p_layout.addWidget(self.btn_delete_preset)

    right_layout.addLayout(bot_p_layout)

    splitter.addWidget(right_widget)
    splitter.setSizes([350, 650])
    layout.addWidget(splitter)

    self.load_presets_list()


def load_presets_list(self):
    self.list_presets.clear()
    self.btn_apply_preset.setEnabled(False)
    self.btn_export_preset.setEnabled(False)
    self.btn_delete_preset.setEnabled(False)
    self.web_preset_detail.setHtml(
        "<h3 style='color:#a6adc8; text-align:center; margin-top:40px;'>Select a Preset on the left to preview or apply</h3>"
    )

    presets = []
    for p in PRESETS_DIR.glob("*.json"):
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
                data["file_path"] = p
                presets.append(data)
        except Exception:
            pass

    presets.sort(key=lambda x: x.get("name", ""))

    for pr in presets:
        item = QListWidgetItem()
        mod_cnt = len(pr.get("mods", []))
        item.setText(f"{pr.get('name', 'Preset')}  ({mod_cnt} mods)")
        item.setData(Qt.UserRole, pr)
        self.list_presets.addItem(item)


def on_preset_selected(self):
    items = self.list_presets.selectedItems()
    if not items:
        self.btn_apply_preset.setEnabled(False)
        self.btn_export_preset.setEnabled(False)
        self.btn_delete_preset.setEnabled(False)
        return

    preset = items[0].data(Qt.UserRole)
    self.current_selected_preset = preset

    self.btn_apply_preset.setEnabled(True)
    self.btn_export_preset.setEnabled(True)
    self.btn_delete_preset.setEnabled(True)

    name = html.escape(preset.get("name", "Preset"))
    desc = html.escape(preset.get("description", "No description provided."))
    ver = html.escape(preset.get("spt_version", getattr(self, "installed_spt_ver", "SPT 4.1.3")))
    created = html.escape(preset.get("created_at", ""))
    mods = preset.get("mods", [])

    mods_table = ""
    for m in mods:
        m_name = m.get("name", "")
        m_raw_title = m.get("title") or m_name
        m_author = m.get("author") or m.get("creator", "Community")
        m_ver = html.escape(str(m.get("version", "")))
        m_type_raw = m.get("type", "Mod")
        m_type = html.escape(m_type_raw)
        m_link = m.get("link")

        if not m_link or m_author == "Community":
            matched = find_best_catalog_match_global(m_name)
            if matched:
                if not m_link and matched.get("link"):
                    m_link = matched.get("link")
                if m_author == "Community" and matched.get("creator"):
                    m_author = matched.get("creator")

        m_author = html.escape(m_author)

        # Disambiguate title if filename/foldername differs
        if m_name and m_raw_title.lower() != m_name.lower():
            m_title = f"{html.escape(m_raw_title)} <span style='color:#89b4fa; font-size:11px;'>({html.escape(m_name)})</span>"
        else:
            m_title = html.escape(m_raw_title)

        # Check package-aware live status against all_installed_mods
        matched_installed = next(
            (
                inst
                for inst in getattr(self, "all_installed_mods", [])
                if inst["name"].lower() == m_raw_title.lower() or inst["name"].lower() == m_name.lower()
            ),
            None,
        )
        if not matched_installed:
            cat_match = find_best_catalog_match_global(m_raw_title) or find_best_catalog_match_global(m_name)
            if cat_match:
                matched_installed = next(
                    (
                        inst
                        for inst in getattr(self, "all_installed_mods", [])
                        if inst["name"].lower() == cat_match["title"].lower()
                    ),
                    None,
                )

        if matched_installed:
            is_enabled = not matched_installed.get("disabled", False)
            is_staged = True
        else:
            is_server = "server" in m_type_raw.lower()
            target_game_dir = SERVER_MODS_DIR if is_server else CLIENT_MODS_DIR
            target_staged_dir = STAGED_SERVER if is_server else STAGED_CLIENT

            is_enabled = (target_game_dir / m_name).exists() or (target_game_dir / m_name).is_symlink()
            is_staged = (target_staged_dir / m_name).exists()

            if not is_enabled and not is_staged:
                st, _ = check_dep_status(m_raw_title)
                is_enabled = st == "ENABLED"
                is_staged = st == "STAGED_DISABLED" or is_enabled

        if is_enabled:
            st_badge = "<span style='color:#a6e3a1; font-weight:bold;'>🟢 Installed && Enabled</span>"
        elif is_staged:
            st_badge = "<span style='color:#fab387; font-weight:bold;'>🟡 Stashed (Disabled)</span>"
        else:
            st_badge = "<span style='color:#f38ba8; font-weight:bold;'>🔴 Missing (Will Auto-Download)</span>"

        link_html = (
            f"<a href='{html.escape(m_link)}' style='color:#89b4fa;'>View Page</a>" if m_link else "Local Package"
        )

        mods_table += f"""
        <tr>
            <td style='padding:6px; border-bottom:1px solid #313244;'><b>{m_title}</b> <span style='color:#a6adc8;'>v{m_ver}</span></td>
            <td style='padding:6px; border-bottom:1px solid #313244; color:#bac2de;'>by {m_author}</td>
            <td style='padding:6px; border-bottom:1px solid #313244;'>{m_type}</td>
            <td style='padding:6px; border-bottom:1px solid #313244;'>{st_badge}</td>
            <td style='padding:6px; border-bottom:1px solid #313244;'>{link_html}</td>
        </tr>
        """

    html_out = f"""
    <div style='padding:12px;'>
        <h2 style='color:#89b4fa; margin:0 0 6px 0;'>{name}</h2>
        <p style='color:#a6adc8; margin:0 0 12px 0;'>Target: <b>{ver}</b> • Total Mods: <b>{len(mods)}</b> • Saved: {created}</p>
        <p style='color:#cdd6f4; background-color:#313244; padding:10px; border-radius:6px; margin-bottom:16px;'>{desc}</p>
        <h3 style='color:#cba6f7; margin-bottom:8px;'>📦 Mods Included in this Preset:</h3>
        <table style='width:100%; border-collapse:collapse; font-size:12px; color:#cdd6f4;'>
            <thead>
                <tr style='background-color:#313244; color:#cdd6f4; text-align:left;'>
                    <th style='padding:6px;'>Mod Name</th>
                    <th style='padding:6px;'>Author</th>
                    <th style='padding:6px;'>Type</th>
                    <th style='padding:6px;'>Current Status</th>
                    <th style='padding:6px;'>Link</th>
                </tr>
            </thead>
            <tbody>
                {mods_table}
            </tbody>
        </table>
    </div>
    """
    self.web_preset_detail.setHtml(html_out)


def create_preset_from_stash(self, *args):
    if not hasattr(self, "all_installed_mods") or not self.all_installed_mods:
        self.load_installed_mods()

    enabled_mods = [m for m in getattr(self, "all_installed_mods", []) if not m.get("disabled", False)]

    if not enabled_mods:
        QMessageBox.warning(self, "No Enabled Mods", "No currently enabled mods were found in your Stash to save.")
        return

    dlg = SavePresetDialog(len(enabled_mods), self)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return

    title, desc = dlg.get_data()
    if not title:
        QMessageBox.warning(self, "Invalid Name", "Preset name cannot be empty.")
        return

    manifest_mods = []
    for mod in enabled_mods:
        staged_p = mod.get("staged_path")
        meta_data = load_mod_meta(staged_p) if staged_p else None
        matched = find_best_catalog_match_global(mod["name"])

        m_title = meta_data.get("title") if meta_data else None
        if not m_title and matched:
            m_title = matched.get("title")
        if not m_title:
            m_title = mod["name"]

        m_author = meta_data.get("author") if meta_data else None
        if (not m_author or m_author == "Community") and matched:
            m_author = matched.get("creator")
        if not m_author:
            m_author = "Community"

        m_link = meta_data.get("link") if meta_data else None
        if not m_link and matched:
            m_link = matched.get("link")
        if not m_link:
            m_link = ""

        m_ver = meta_data.get("version") if meta_data else None
        if not m_ver and matched:
            m_ver = matched.get("version")
        if not m_ver:
            m_ver = "1.0.0"

        m_img = meta_data.get("image_url") if meta_data else None
        if not m_img and matched:
            m_img = matched.get("image_url")
        if not m_img:
            m_img = ""

        m_cat = meta_data.get("category") if meta_data else None
        if not m_cat and matched:
            m_cat = matched.get("category")
        if not m_cat:
            m_cat = "Other"

        manifest_mods.append(
            {
                "name": mod["name"],
                "title": m_title,
                "author": m_author,
                "version": m_ver,
                "type": mod["type"],
                "image_url": m_img,
                "link": m_link,
                "category": m_cat,
                "description": meta_data.get("description", "") if meta_data else "",
                "enabled": True,
            }
        )

    preset_data = {
        "manifest_version": "1.0",
        "app": "SPT Stash",
        "name": title,
        "description": desc,
        "spt_version": getattr(self, "installed_spt_ver", "SPT 4.1.3"),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mods": manifest_mods,
    }

    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", title.lower())
    out_file = PRESETS_DIR / f"{safe_id}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(preset_data, f, indent=2)

    self.load_presets_list()
    QMessageBox.information(
        self,
        "Preset Created",
        f"✅ Saved preset <b>{html.escape(title)}</b> with <b>{len(manifest_mods)} active mod(s)</b>!",
    )


def apply_selected_preset(self):
    if not hasattr(self, "current_selected_preset") or not self.current_selected_preset:
        return

    preset = self.current_selected_preset
    manifest_mods = preset.get("mods", [])

    # Build set of desired enabled mod names (case-insensitive)
    desired_enabled_names = set(m["name"].lower() for m in manifest_mods if m.get("enabled", True))

    enabled_count = 0
    disabled_count = 0

    # Scan all staged mods in Stash
    staged_dirs = [("client", STAGED_CLIENT, CLIENT_MODS_DIR), ("server", STAGED_SERVER, SERVER_MODS_DIR)]

    for m_type, staged_base, game_base in staged_dirs:
        if not staged_base.exists():
            continue
        for staged_item in staged_base.iterdir():
            if staged_item.name.startswith("."):
                continue

            item_name_lower = staged_item.name.lower()
            game_target = game_base / staged_item.name

            should_be_enabled = item_name_lower in desired_enabled_names

            if should_be_enabled:
                if not (game_target.is_symlink() or game_target.exists()):
                    os.symlink(str(staged_item), str(game_target))
                    enabled_count += 1
            else:
                if game_target.is_symlink() or game_target.exists():
                    if game_target.is_symlink() or not game_target.is_dir():
                        game_target.unlink()
                    else:
                        shutil.rmtree(game_target)
                    disabled_count += 1

    # Check for any missing catalog mods that are not in Stash
    missing_mods = []
    for m in manifest_mods:
        if m.get("enabled", True):
            m_name = m["name"].lower()
            m_type = m.get("type", "")
            is_server = "server" in m_type.lower()
            target_staged = STAGED_SERVER if is_server else STAGED_CLIENT

            in_stash = (target_staged / m["name"]).exists() or (
                target_staged.exists() and any(p.name.lower() == m_name for p in target_staged.iterdir())
            )
            if not in_stash:
                missing_mods.append(m)

    self.load_installed_mods()
    self.on_preset_selected()

    if missing_mods:
        mod_names = "\n".join(f"• {m.get('title') or m['name']}" for m in missing_mods)
        reply = QMessageBox.question(
            self,
            "Auto-Download Missing Preset Mods?",
            f"Preset <b>{html.escape(preset.get('name', 'Preset'))}</b> includes <b>{len(missing_mods)} missing mod(s)</b>:\n\n"
            f"{mod_names}\n\n"
            f"Would you like to automatically download and install these missing mods now?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.start_dependency_queue_download(missing_mods, None)
            return

    QMessageBox.information(
        self, "Preset Applied", f"⚡ Preset <b>{html.escape(preset.get('name', 'Preset'))}</b> successfully applied!"
    )


def export_selected_preset(self):
    if not hasattr(self, "current_selected_preset") or not self.current_selected_preset:
        return

    preset = self.current_selected_preset
    html_out = generate_html_stash_manifest(preset)

    clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", preset.get("name", "preset").lower())
    file_path, _ = QFileDialog.getSaveFileName(
        self,
        "Export Preset HTML Manifest",
        str(Path.home() / f"{clean_name}.html"),
        "HTML Manifest Files (*.html);;JSON Manifest Files (*.json)",
    )
    if not file_path:
        return

    try:
        p = Path(file_path)
        if p.suffix.lower() == ".json":
            p.write_text(json.dumps(preset, indent=2), encoding="utf-8")
        else:
            p.write_text(html_out, encoding="utf-8")
        QMessageBox.information(self, "Export Complete", f"✅ Preset exported to <b>{html.escape(str(p))}</b>")
    except Exception as e:
        QMessageBox.critical(self, "Export Error", f"Failed to export preset: {e}")


def import_preset_file(self):
    file_path, _ = QFileDialog.getOpenFileName(
        self, "Import Preset File", str(Path.home()), "SPT Manifest Files (*.html *.json);;All Files (*)"
    )
    if not file_path:
        return

    try:
        p = Path(file_path)
        content = p.read_text(encoding="utf-8")
        if p.suffix.lower() == ".html":
            m = re.search(
                r'<script id="stash-manifest-data" type="application/json">\s*(.*?)\s*</script>', content, re.DOTALL
            )
            if not m:
                QMessageBox.critical(self, "Import Error", "Could not find embedded manifest data in this HTML file.")
                return
            preset_data = json.loads(m.group(1))
        else:
            preset_data = json.loads(content)

        preset_name = preset_data.get("name") or preset_data.get("title") or p.stem
        preset_data["name"] = preset_name
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", preset_name.lower())
        out_file = PRESETS_DIR / f"{safe_id}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(preset_data, f, indent=2)

        self.load_presets_list()
        QMessageBox.information(
            self, "Import Complete", f"✅ Imported preset <b>{html.escape(preset_name)}</b> into Presets library!"
        )
    except Exception as e:
        QMessageBox.critical(self, "Import Error", f"Failed to import preset: {e}")


def delete_selected_preset(self):
    if not hasattr(self, "current_selected_preset") or not self.current_selected_preset:
        return

    preset = self.current_selected_preset
    file_p = preset.get("file_path")

    reply = QMessageBox.question(
        self,
        "Delete Preset?",
        f"Are you sure you want to delete preset <b>{html.escape(preset.get('name', 'Preset'))}</b>?",
        QMessageBox.Yes | QMessageBox.No,
    )
    if reply == QMessageBox.Yes:
        if file_p and Path(file_p).exists():
            Path(file_p).unlink()
        self.load_presets_list()


def export_stash_manifest(self):
    if not hasattr(self, 'all_installed_mods') or not self.all_installed_mods:
        QMessageBox.information(self, "Export Stash Manifest", "No installed mods found to export.")
        return

    file_path, _ = QFileDialog.getSaveFileName(
        self, "Export Stash Manifest", str(Path.home() / "stash_manifest.html"), "HTML Files (*.html)"
    )
    if not file_path:
        return

    catalog_mods = getattr(self, 'remote_mods', [])
    if not catalog_mods and CATALOG_CACHE_FILE.exists():
        try:
            with open(CATALOG_CACHE_FILE, "r", encoding="utf-8") as f:
                catalog_mods = json.load(f)
        except Exception:
            catalog_mods = []

    manifest_mods = []
    for mod in self.all_installed_mods:
        staged_p = mod.get("staged_path")
        meta_data = load_mod_meta(staged_p) if staged_p else None

        if meta_data and meta_data.get("link"):
            manifest_mods.append({
                "name": mod["name"],
                "title": meta_data.get("title", mod["name"]),
                "author": meta_data.get("author", "Community"),
                "version": meta_data.get("version", "1.0.0"),
                "type": mod["type"],
                "image_url": meta_data.get("image_url", ""),
                "link": meta_data.get("link", ""),
                "category": meta_data.get("category", "Other"),
                "description": meta_data.get("description", ""),
                "enabled": not mod["disabled"]
            })
        else:
            matched = find_best_catalog_match_global(mod["name"])
            if matched:
                manifest_mods.append({
                    "name": mod["name"],
                    "title": matched.get("title", mod["name"]),
                    "author": matched.get("creator", "Community"),
                    "version": matched.get("version", "1.0.0"),
                    "type": mod["type"],
                    "image_url": matched.get("image_url", ""),
                    "link": matched.get("link", ""),
                    "category": matched.get("category", "Other"),
                    "description": matched.get("description", ""),
                    "enabled": not mod["disabled"]
                })
            else:
                clean_disp = re.sub(r'([a-z])([A-Z])', r'\1 \2', re.sub(r'\.dll$', '', mod['name'], flags=re.I))
                manifest_mods.append({
                    "name": mod["name"],
                    "title": clean_disp,
                    "author": "Community",
                    "version": "1.0.0",
                    "type": mod["type"],
                    "image_url": "",
                    "link": f"https://sp-mod.com/mods?query={urllib.parse.quote(clean_disp)}",
                    "category": "Other",
                    "description": f"Installed mod package ({mod['name']})",
                    "enabled": not mod["disabled"]
                })

    manifest = {
        "manifest_version": "1.0",
        "app": "SPT Stash",
        "spt_version": getattr(self, 'installed_spt_ver', 'SPT 4.1.3'),
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mods": manifest_mods
    }

    html_out = generate_html_stash_manifest(manifest)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_out)
        QMessageBox.information(self, "Export Successful", f"✅ Stash Manifest successfully saved to:\n{file_path}\n\nYou can open this file in any browser or share it with friends!")
    except Exception as e:
        QMessageBox.critical(self, "Export Error", f"Failed to save manifest: {e}")


def import_stash_manifest(self):
    file_path, _ = QFileDialog.getOpenFileName(
        self, "Import Stash Manifest", str(Path.home()), "HTML / Manifest Files (*.html *.json)"
    )
    if not file_path or not Path(file_path).exists():
        return

    try:
        content = Path(file_path).read_text(encoding="utf-8")
        m = re.search(r'<script id=[\"\']stash-manifest-data[\"\'] type=[\"\']application/json[\"\']>\s*(.*?)\s*</script>', content, re.DOTALL)
        if m:
            json_str = m.group(1)
        else:
            json_str = content

        manifest = json.loads(json_str)
        manifest_mods = manifest.get("mods", [])
    except Exception as e:
        QMessageBox.critical(self, "Import Error", f"Failed to parse Stash Manifest: {e}")
        return

    if not manifest_mods:
        QMessageBox.warning(self, "Import Warning", "No mod definitions found in this manifest.")
        return

    missing_mods = []
    staged_disabled_mods = []

    for m_mod in manifest_mods:
        st, path = check_dep_status(m_mod.get("title") or m_mod.get("name"))
        if st == "MISSING":
            missing_mods.append(m_mod)
        elif st == "STAGED_DISABLED" and m_mod.get("enabled", True):
            staged_disabled_mods.append({"title": m_mod.get("title") or m_mod["name"], "path": path})

    if staged_disabled_mods:
        for d in staged_disabled_mods:
            dep_p = d["path"]
            is_srv = "server" in str(dep_p).lower()
            link_p = (SERVER_MODS_DIR if is_srv else CLIENT_MODS_DIR) / dep_p.name
            if link_p.is_symlink() or link_p.exists():
                if link_p.is_symlink() or not link_p.is_dir():
                    link_p.unlink()
                else:
                    shutil.rmtree(link_p)
            os.symlink(str(dep_p), str(link_p))
        self.load_installed_mods()

    if missing_mods:
        mod_names = "\n".join(f"• {m.get('title') or m['name']}" for m in missing_mods)
        reply = QMessageBox.question(
            self,
            "Missing Mods Detected",
            f"The manifest contains <b>{len(missing_mods)}</b> mod(s) not found in your stash:\n\n{mod_names}\n\nWould you like to search sp-mod.com to download them?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.tabs.setCurrentIndex(2)
            first = missing_mods[0]
            self.txt_browse_search.setText(first.get("title") or first.get("name"))
    else:
        QMessageBox.information(self, "Import Complete", "✅ All manifest mods are installed and enabled!")


# ------------------ Browse Tab (sp-mod.com) ------------------
