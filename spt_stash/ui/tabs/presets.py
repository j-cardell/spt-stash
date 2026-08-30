#!/usr/bin/env python3
"""SPT Stash — Presets & Manifests tab (V4 layout)."""

import html
import json
import re
import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
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
from ...staging.links import create_relative_symlink
from ...staging.metadata import load_mod_meta
from ..dialogs import SavePresetDialog
from ..widgets import _nav_pixmap


def setup_presets_tab(self):
    layout = QVBoxLayout(self.tab_presets)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(12)

    #  Top Row
    top_row = QHBoxLayout()
    top_row.setSpacing(10)

    lbl_title = QLabel("Presets & Manifests")
    lbl_title.setStyleSheet("font-size: 18px; font-weight: 700; letter-spacing: -0.02em;")
    top_row.addWidget(lbl_title)

    self.lbl_presets_summary = QLabel("0 saved presets")
    self.lbl_presets_summary.setStyleSheet("color: #7f8698; font-size: 12px; margin-left: 4px;")
    top_row.addWidget(self.lbl_presets_summary)

    top_row.addStretch()

    btn_new_preset = QPushButton("+ Save Current Setup as Preset")
    btn_new_preset.setProperty("role", "primary")
    btn_new_preset.setProperty("size", "sm")
    btn_new_preset.clicked.connect(lambda: self.create_preset_from_stash())
    top_row.addWidget(btn_new_preset)

    btn_import_p = QPushButton("Import File")
    btn_import_p.setProperty("role", "ghost")
    btn_import_p.setProperty("size", "sm")
    btn_import_p.clicked.connect(lambda: self.import_preset_file())
    top_row.addWidget(btn_import_p)

    btn_refresh_p = QPushButton("↻")
    btn_refresh_p.setProperty("role", "ghost")
    btn_refresh_p.setProperty("size", "sm")
    btn_refresh_p.setToolTip("Refresh presets list")
    btn_refresh_p.clicked.connect(lambda: self.load_presets_list())
    top_row.addWidget(btn_refresh_p)

    layout.addLayout(top_row)

    #  Splitter: Presets List & Preview Detail
    splitter = QSplitter(Qt.Horizontal)
    splitter.setStyleSheet("QSplitter::handle { background-color: #232733; width: 1px; }")

    self.list_presets = QListWidget()
    self.list_presets.setSpacing(2)
    self.list_presets.itemSelectionChanged.connect(self.on_preset_selected)
    splitter.addWidget(self.list_presets)

    right_widget = QWidget()
    right_layout = QVBoxLayout(right_widget)
    right_layout.setContentsMargins(12, 0, 0, 0)
    right_layout.setSpacing(10)

    self.web_preset_detail = QTextBrowser()
    self.web_preset_detail.setOpenExternalLinks(True)
    self.web_preset_detail.setStyleSheet(
        "background-color: #14161d; border: 1px solid #232733; border-radius: 8px; color: #eceef3; padding: 12px;"
    )
    right_layout.addWidget(self.web_preset_detail)

    bot_p_layout = QHBoxLayout()
    bot_p_layout.setSpacing(8)

    self.btn_apply_preset = QPushButton(" Apply Preset to Game")
    self.btn_apply_preset.setProperty("role", "success")
    self.btn_apply_preset.setProperty("size", "lg")
    self.btn_apply_preset.clicked.connect(self.apply_selected_preset)
    self.btn_apply_preset.setEnabled(False)
    self.btn_apply_preset.setIcon(QIcon(_nav_pixmap("install", size=14, color="#4ade80")))
    self.btn_apply_preset.setIconSize(QSize(14, 14))
    bot_p_layout.addWidget(self.btn_apply_preset)

    self.btn_export_preset = QPushButton("Export HTML")
    self.btn_export_preset.setProperty("role", "ghost")
    self.btn_export_preset.setProperty("size", "lg")
    self.btn_export_preset.clicked.connect(self.export_selected_preset)
    self.btn_export_preset.setEnabled(False)
    bot_p_layout.addWidget(self.btn_export_preset)

    self.btn_delete_preset = QPushButton("Delete")
    self.btn_delete_preset.setProperty("role", "danger")
    self.btn_delete_preset.setProperty("size", "lg")
    self.btn_delete_preset.clicked.connect(self.delete_selected_preset)
    self.btn_delete_preset.setEnabled(False)
    self.btn_delete_preset.setIcon(QIcon(_nav_pixmap("trash", size=14, color="#f87171")))
    self.btn_delete_preset.setIconSize(QSize(14, 14))
    bot_p_layout.addWidget(self.btn_delete_preset)

    right_layout.addLayout(bot_p_layout)

    splitter.addWidget(right_widget)
    splitter.setSizes([320, 680])
    layout.addWidget(splitter)

    self.load_presets_list()


def load_presets_list(self):
    self.list_presets.clear()
    self.btn_apply_preset.setEnabled(False)
    self.btn_export_preset.setEnabled(False)
    self.btn_delete_preset.setEnabled(False)
    self.web_preset_detail.setHtml(
        "<div style='color:#7f8698; text-align:center; margin-top:80px; font-size:14px;'>"
        "Select a Preset on the left to preview its components and status"
        "</div>"
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

    if hasattr(self, "lbl_presets_summary"):
        self.lbl_presets_summary.setText(f"{len(presets)} saved presets")

    for pr in presets:
        item = QListWidgetItem()
        mod_cnt = len(pr.get("mods", []))
        item.setText(f"{pr.get('name', 'Preset')}\n{mod_cnt} mods · {pr.get('spt_version', 'SPT 4.1.3')}")
        item.setData(Qt.UserRole, pr)
        self.list_presets.addItem(item)

    self.list_presets.setStyleSheet("""
    QListWidget {
        background-color: #0f1016;
        border: none;
        border-right: 1px solid #232733;
        outline: none;
    }
    QListWidget::item {
        color: #eceef3;
        padding: 12px 14px;
        border-bottom: 1px solid #232733;
        border-left: 3px solid transparent;
    }
    QListWidget::item:hover {
        background-color: #14161d;
    }
    QListWidget::item:selected {
        background-color: #1a1d27;
        border-left: 3px solid #7c8cff;
        padding-left: 11px;
    }
    """)


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

        if m_name and m_raw_title.lower() != m_name.lower():
            m_title = f"{html.escape(m_raw_title)} <span style='color:#7c8cff; font-size:11px;'>({html.escape(m_name)})</span>"
        else:
            m_title = html.escape(m_raw_title)

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
            st_badge = "<span style='color:#4ade80; font-weight:600;'> Enabled</span>"
        elif is_staged:
            st_badge = "<span style='color:#fbbf24; font-weight:600;'> Disabled in Stash</span>"
        else:
            st_badge = "<span style='color:#f87171; font-weight:600;'> Missing</span>"

        link_html = (
            f"<a href='{html.escape(m_link)}' style='color:#7c8cff; text-decoration:none;'>View</a>" if m_link else "Local"
        )

        mods_table += f"""
        <tr>
            <td style='padding:8px 6px; border-bottom:1px solid #232733;'><b>{m_title}</b> <span style='color:#7f8698;'>v{m_ver}</span></td>
            <td style='padding:8px 6px; border-bottom:1px solid #232733; color:#7f8698;'>by {m_author}</td>
            <td style='padding:8px 6px; border-bottom:1px solid #232733;'>{m_type}</td>
            <td style='padding:8px 6px; border-bottom:1px solid #232733;'>{st_badge}</td>
            <td style='padding:8px 6px; border-bottom:1px solid #232733;'>{link_html}</td>
        </tr>
        """

    html_content = f"""
    <html>
    <body style='font-family:"Segoe UI", Inter, sans-serif; background-color:#14161d; color:#eceef3; padding:10px;'>
        <div style='border-bottom:1px solid #232733; padding-bottom:12px; margin-bottom:14px;'>
            <h2 style='color:#eceef3; margin:0 0 6px 0;'>{name}</h2>
            <div style='color:#7f8698; font-size:12px; margin-bottom:8px;'>
                <b>SPT Target:</b> <span style='color:#7c8cff;'>{ver}</span> &nbsp;|&nbsp;
                <b>Created:</b> {created} &nbsp;|&nbsp;
                <b>Total Mods:</b> {len(mods)}
            </div>
            <div style='color:#bac2de; font-size:13px;'>{desc}</div>
        </div>

        <h3 style='color:#eceef3; margin:14px 0 8px 0; font-size:14px;'>Configured Mod Components ({len(mods)})</h3>
        <table style='width:100%; border-collapse:collapse; font-size:12.5px;'>
            <thead>
                <tr style='background-color:#1a1d27; color:#7f8698; text-align:left;'>
                    <th style='padding:8px 6px;'>Mod Name</th>
                    <th style='padding:8px 6px;'>Author</th>
                    <th style='padding:8px 6px;'>Type</th>
                    <th style='padding:8px 6px;'>Local Status</th>
                    <th style='padding:8px 6px;'>Link</th>
                </tr>
            </thead>
            <tbody>
                {mods_table}
            </tbody>
        </table>
    </body>
    </html>
    """
    self.web_preset_detail.setHtml(html_content)


def create_preset_from_stash(self):
    active_mods = []
    for mod in getattr(self, "all_installed_mods", []):
        if not mod.get("disabled", False):
            meta = load_mod_meta(mod["staged_path"]) or {}
            matched = find_best_catalog_match_global(mod["name"])

            title = meta.get("title") or (matched.get("title") if matched else mod["name"])
            author = meta.get("author") or (matched.get("creator") if matched else "Community")
            version = meta.get("version") or (matched.get("version") if matched else "1.0.0")
            link = meta.get("link") or (matched.get("link") if matched else "")

            mod_item = {
                "name": mod["name"],
                "title": title,
                "author": author,
                "version": version,
                "type": mod["type"],
                "link": link,
            }
            active_mods.append(mod_item)

    if not active_mods:
        QMessageBox.warning(self, "No Active Mods", "No currently enabled mods were found in your Stash.")
        return

    dialog = SavePresetDialog(len(active_mods), getattr(self, "installed_spt_ver", "SPT 4.1.3"), self)
    if dialog.exec() == QDialog.Accepted:
        preset_name, desc = dialog.get_data()
        safe_name = re.sub(r'[\/*?:"<>|]', "", preset_name).strip()
        if not safe_name:
            safe_name = "Untitled_Preset"

        preset_data = {
            "name": preset_name,
            "description": desc,
            "spt_version": getattr(self, "installed_spt_ver", "SPT 4.1.3"),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mods": active_mods,
        }

        save_path = PRESETS_DIR / f"{safe_name}.json"
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(preset_data, f, indent=2)
            self.load_presets_list()
            if hasattr(self, "toast"):
                self.toast.success(f"Preset '{preset_name}' saved!")
            else:
                QMessageBox.information(self, "Preset Saved", f"Preset <b>{preset_name}</b> saved successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed saving preset file: {e}")


def apply_selected_preset(self):
    if not hasattr(self, "current_selected_preset") or not self.current_selected_preset:
        return

    preset = self.current_selected_preset
    preset_name = preset.get("name", "Preset")
    preset_mods = preset.get("mods", [])

    reply = QMessageBox.question(
        self,
        "Apply Preset",
        f"Are you sure you want to apply preset <b>{preset_name}</b>?<br><br>"
        f"This will synchronize your live game symlinks with the <b>{len(preset_mods)} mods</b> defined in this preset.",
        QMessageBox.Yes | QMessageBox.No,
    )
    if reply != QMessageBox.Yes:
        return

    missing_mods = []
    for m in preset_mods:
        m_name = m.get("name", "")
        m_type = m.get("type", "Mod")
        is_server = "server" in m_type.lower()
        target_staged_dir = STAGED_SERVER if is_server else STAGED_CLIENT

        if not (target_staged_dir / m_name).exists():
            missing_mods.append(m)

    if missing_mods:
        miss_str = "\n".join(f"• {m.get('title', m.get('name'))}" for m in missing_mods[:10])
        extra = f"\n...and {len(missing_mods)-10} more" if len(missing_mods) > 10 else ""
        rep = QMessageBox.question(
            self,
            "Missing Preset Mods",
            f"<b>{len(missing_mods)} mod(s)</b> from this preset are not installed in your Stash:\n\n"
            f"{miss_str}{extra}\n\n"
            f"Would you like to automatically download and stage these missing mods now?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if rep == QMessageBox.Yes:
            download_queue = []
            for m in missing_mods:
                m_title = m.get("title", m.get("name"))
                matched = find_best_catalog_match_global(m_title) or find_best_catalog_match_global(m.get("name"))
                if matched and matched.get("download_url"):
                    download_queue.append(matched)

            if download_queue:
                self.start_dependency_queue_download(download_queue, None)
                QMessageBox.information(
                    self,
                    "Downloading Missing Mods",
                    f"Initiated download of <b>{len(download_queue)} missing mod(s)</b>.<br>Please wait for downloads to complete and then apply the preset again.",
                )
                return

    for f in CLIENT_MODS_DIR.iterdir():
        if f.is_symlink():
            f.unlink()
    for f in SERVER_MODS_DIR.iterdir():
        if f.is_symlink():
            f.unlink()

    enabled_count = 0
    for m in preset_mods:
        m_name = m.get("name", "")
        m_type = m.get("type", "Mod")
        is_server = "server" in m_type.lower()

        if is_server:
            staged_p = STAGED_SERVER / m_name
            live_p = SERVER_MODS_DIR / m_name
        else:
            staged_p = STAGED_CLIENT / m_name
            live_p = CLIENT_MODS_DIR / m_name

        if staged_p.exists():
            create_relative_symlink(staged_p, live_p)
            enabled_count += 1

    self.load_installed_mods()
    self.on_preset_selected()
    if hasattr(self, "toast"):
        self.toast.success(f" Applied preset '{preset_name}' ({enabled_count} mods enabled)")
    else:
        QMessageBox.information(
            self,
            "Preset Applied",
            f" Preset <b>{preset_name}</b> applied successfully!<br><br>"
            f"<b>{enabled_count} mod component(s)</b> enabled in live game.",
        )


def export_selected_preset(self):
    if not hasattr(self, "current_selected_preset") or not self.current_selected_preset:
        return

    preset = self.current_selected_preset
    name = preset.get("name", "Preset")
    safe_name = re.sub(r'[\/*?:"<>|]', "", name).strip() or "Preset"

    file_path, _ = QFileDialog.getSaveFileName(
        self, "Export Preset HTML Manifest", f"{safe_name}_manifest.html", "HTML Files (*.html);;All Files (*)"
    )
    if not file_path:
        return

    try:
        html_out = generate_html_stash_manifest(
            manifest_title=f"SPT Stash Preset — {name}",
            installed_spt_version=preset.get("spt_version", "SPT 4.1.3"),
            active_mods=preset.get("mods", []),
            catalog_cache_file=CATALOG_CACHE_FILE,
        )
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_out)
        if hasattr(self, "toast"):
            self.toast.success(f" Exported preset manifest to {Path(file_path).name}")
        else:
            QMessageBox.information(self, "Export Complete", f"Preset manifest exported to:\n\n{file_path}")
    except Exception as e:
        QMessageBox.critical(self, "Export Error", f"Failed exporting preset manifest: {e}")


def import_preset_file(self):
    file_path, _ = QFileDialog.getOpenFileName(
        self, "Import Preset JSON File", "", "JSON Files (*.json *.html);;All Files (*)"
    )
    if not file_path:
        return

    p = Path(file_path)
    try:
        if p.suffix.lower() == ".html":
            content = p.read_text(encoding="utf-8")
            match = re.search(r'<script id="manifest-data" type="application/json">\s*(\{.*?\})\s*</script>', content, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
            else:
                QMessageBox.critical(self, "Import Error", "Could not find valid manifest data inside the selected HTML file.")
                return
        else:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)

        if "name" not in data or "mods" not in data:
            QMessageBox.critical(self, "Invalid Preset", "The selected file is not a valid SPT Stash preset JSON.")
            return

        name = data.get("name", p.stem)
        safe_name = re.sub(r'[\/*?:"<>|]', "", name).strip() or p.stem
        target_path = PRESETS_DIR / f"{safe_name}.json"

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        self.load_presets_list()
        if hasattr(self, "toast"):
            self.toast.success(f" Imported preset '{name}'")
        else:
            QMessageBox.information(self, "Preset Imported", f"Preset <b>{name}</b> imported successfully!")
    except Exception as e:
        QMessageBox.critical(self, "Import Error", f"Failed importing preset: {e}")


def delete_selected_preset(self):
    if not hasattr(self, "current_selected_preset") or not self.current_selected_preset:
        return

    preset = self.current_selected_preset
    name = preset.get("name", "Preset")
    file_path = preset.get("file_path")

    reply = QMessageBox.question(
        self,
        "Delete Preset",
        f"Are you sure you want to permanently delete preset <b>{name}</b>?",
        QMessageBox.Yes | QMessageBox.No,
    )
    if reply == QMessageBox.Yes and file_path:
        try:
            Path(file_path).unlink()
            self.load_presets_list()
            if hasattr(self, "toast"):
                self.toast.error(f" Deleted preset '{name}'")
            else:
                QMessageBox.information(self, "Preset Deleted", f"Preset <b>{name}</b> was deleted.")
        except Exception as e:
            QMessageBox.critical(self, "Delete Error", f"Failed deleting preset: {e}")


def export_stash_manifest(self):
    active_mods = []
    for mod in getattr(self, "all_installed_mods", []):
        meta = load_mod_meta(mod["staged_path"]) or {}
        matched = find_best_catalog_match_global(mod["name"])

        title = meta.get("title") or (matched.get("title") if matched else mod["name"])
        author = meta.get("author") or (matched.get("creator") if matched else "Community")
        version = meta.get("version") or (matched.get("version") if matched else "1.0.0")
        link = meta.get("link") or (matched.get("link") if matched else "")

        mod_item = {
            "name": mod["name"],
            "title": title,
            "author": author,
            "version": version,
            "type": mod["type"],
            "link": link,
            "enabled": not mod.get("disabled", False),
        }
        active_mods.append(mod_item)

    file_path, _ = QFileDialog.getSaveFileName(
        self, "Export Stash HTML Manifest", "spt_stash_manifest.html", "HTML Files (*.html);;All Files (*)"
    )
    if not file_path:
        return

    try:
        html_out = generate_html_stash_manifest(
            manifest_title="SPT Stash — Installed Mods Manifest",
            installed_spt_version=getattr(self, "installed_spt_ver", "SPT 4.1.3"),
            active_mods=active_mods,
            catalog_cache_file=CATALOG_CACHE_FILE,
        )
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_out)
        if hasattr(self, "toast"):
            self.toast.success(f" Exported manifest to {Path(file_path).name}")
        else:
            QMessageBox.information(self, "Export Complete", f"Stash manifest exported to:\n\n{file_path}")
    except Exception as e:
        QMessageBox.critical(self, "Export Error", f"Failed exporting manifest: {e}")


def import_stash_manifest(self):
    self.import_preset_file()
