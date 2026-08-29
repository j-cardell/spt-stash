#!/usr/bin/env python3
"""SPT Stash — Installed Mods tab."""

import html
import os
import re
import shutil
import subprocess
import urllib.request

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...catalog.dependencies import (
    fetch_mod_dependencies_sync,
)
from ...catalog.matching import (
    find_best_catalog_match_global,
    resolve_author_profile_url,
)
from ...paths import (
    CLIENT_MODS_DIR,
    SERVER_MODS_DIR,
    STAGED_CLIENT,
    STAGED_SERVER,
)
from ...staging.links import create_relative_symlink, purge_mod_files_and_symlinks
from ...staging.metadata import load_mod_meta, save_mod_meta
from ...staging.workers import FikaSyncThread
from ...version import is_version_newer


def setup_installed_tab(self):
    layout = QVBoxLayout(self.tab_installed)

    top_controls = QHBoxLayout()
    self.installed_search = QLineEdit()
    self.installed_search.setPlaceholderText("Filter installed mods...")
    self.installed_search.textChanged.connect(self.filter_installed_mods)
    top_controls.addWidget(self.installed_search)

    btn_check_updates = QPushButton("🔄 Check for Updates")
    btn_check_updates.clicked.connect(lambda: self.check_installed_mod_updates())
    top_controls.addWidget(btn_check_updates)

    btn_audit = QPushButton("🔍 Audit Dependencies")
    btn_audit.clicked.connect(self.audit_installed_dependencies)
    top_controls.addWidget(btn_audit)

    btn_refresh = QPushButton("🔄 Refresh Installed Mods")
    btn_refresh.clicked.connect(self.load_installed_mods)
    top_controls.addWidget(btn_refresh)

    btn_export = QPushButton("📤 Export Manifest")
    btn_export.clicked.connect(self.export_stash_manifest)
    top_controls.addWidget(btn_export)

    btn_import = QPushButton("📥 Import Manifest")
    btn_import.clicked.connect(self.import_stash_manifest)
    top_controls.addWidget(btn_import)

    layout.addLayout(top_controls)

    self.table_mods = QTableWidget()
    self.table_mods.setColumnCount(7)
    self.table_mods.setHorizontalHeaderLabels(
        ["Status", "Mod Name", "Version", "Type", "Fika Co-Op", "Author", "Actions"]
    )
    self.table_mods.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
    self.table_mods.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
    self.table_mods.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
    self.table_mods.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
    self.table_mods.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
    self.table_mods.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
    self.table_mods.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)
    self.table_mods.setColumnWidth(6, 185)
    self.table_mods.setSelectionMode(QAbstractItemView.ExtendedSelection)
    self.table_mods.setSelectionBehavior(QAbstractItemView.SelectRows)
    self.table_mods.setSortingEnabled(True)
    self.table_mods.horizontalHeader().setSortIndicatorShown(True)
    self.table_mods.horizontalHeader().setSectionsClickable(True)
    self.table_mods.setContextMenuPolicy(Qt.CustomContextMenu)
    self.table_mods.customContextMenuRequested.connect(self.show_installed_table_context_menu)
    self.table_mods.cellClicked.connect(self.on_installed_table_cell_clicked)
    self.table_mods.itemSelectionChanged.connect(self.update_bulk_actions_bar)
    layout.addWidget(self.table_mods)

    # Bulk Actions Bar
    bulk_bar = QHBoxLayout()

    self.lbl_selected_count = QLabel("0 mod(s) selected")
    self.lbl_selected_count.setStyleSheet("color: #a6adc8; font-weight: bold; padding: 4px 8px;")
    bulk_bar.addWidget(self.lbl_selected_count)

    btn_select_all = QPushButton("☑️ Select All")
    btn_select_all.setFixedHeight(36)
    btn_select_all.clicked.connect(lambda: self.select_all_installed_mods())
    bulk_bar.addWidget(btn_select_all)

    btn_deselect_all = QPushButton("☐ Deselect All")
    btn_deselect_all.setFixedHeight(36)
    btn_deselect_all.clicked.connect(lambda: self.deselect_all_installed_mods())
    bulk_bar.addWidget(btn_deselect_all)

    bulk_bar.addStretch()

    self.btn_bulk_enable = QPushButton("▶ Enable Selected")
    self.btn_bulk_enable.setFixedHeight(36)
    self.btn_bulk_enable.setFixedWidth(160)
    self.btn_bulk_enable.setStyleSheet("""
        QPushButton { background-color: #27392b; color: #a6e3a1; border: 1px solid #36503c; font-size: 13px; font-weight: bold; border-radius: 6px; }
        QPushButton:hover { background-color: #314a38; border-color: #a6e3a1; }
        QPushButton:disabled { background-color: #1e1e2e; color: #585b70; border: 1px solid #313244; }
    """)
    self.btn_bulk_enable.clicked.connect(lambda: self.bulk_enable_selected())
    self.btn_bulk_enable.setEnabled(False)
    bulk_bar.addWidget(self.btn_bulk_enable)

    self.btn_bulk_disable = QPushButton("⏸ Disable Selected")
    self.btn_bulk_disable.setFixedHeight(36)
    self.btn_bulk_disable.setFixedWidth(160)
    self.btn_bulk_disable.setStyleSheet("""
        QPushButton { background-color: #3b2d24; color: #fab387; border: 1px solid #543f31; font-size: 13px; font-weight: bold; border-radius: 6px; }
        QPushButton:hover { background-color: #4a392e; border-color: #fab387; }
        QPushButton:disabled { background-color: #1e1e2e; color: #585b70; border: 1px solid #313244; }
    """)
    self.btn_bulk_disable.clicked.connect(lambda: self.bulk_disable_selected())
    self.btn_bulk_disable.setEnabled(False)
    bulk_bar.addWidget(self.btn_bulk_disable)

    self.btn_bulk_delete = QPushButton("🗑 Delete Selected")
    self.btn_bulk_delete.setFixedHeight(36)
    self.btn_bulk_delete.setFixedWidth(160)
    self.btn_bulk_delete.setStyleSheet("""
        QPushButton { background-color: #3a232e; color: #f38ba8; border: 1px solid #542f3e; font-size: 13px; font-weight: bold; border-radius: 6px; }
        QPushButton:hover { background-color: #4a2c3b; border-color: #f38ba8; }
        QPushButton:disabled { background-color: #1e1e2e; color: #585b70; border: 1px solid #313244; }
    """)
    self.btn_bulk_delete.clicked.connect(lambda: self.bulk_delete_selected())
    self.btn_bulk_delete.setEnabled(False)
    bulk_bar.addWidget(self.btn_bulk_delete)

    layout.addLayout(bulk_bar)

    self.load_installed_mods()


def load_installed_mods(self):
    self.table_mods.setRowCount(0)
    mods_map = {}

    client_items = list(STAGED_CLIENT.iterdir()) if STAGED_CLIENT.exists() else []
    server_items = list(STAGED_SERVER.iterdir()) if STAGED_SERVER.exists() else []

    def get_mod_group_key(item):
        meta = load_mod_meta(item) or {}
        matched = find_best_catalog_match_global(item.name)

        if matched and matched.get("title"):
            official_title = matched.get("title").strip()
            if meta.get("title") != official_title or not meta.get("link"):
                meta["title"] = official_title
                meta["link"] = matched.get("link", meta.get("link", ""))
                meta["author"] = matched.get("creator", meta.get("author", ""))
                meta["version"] = matched.get("version", meta.get("version", "1.0.0"))
                save_mod_meta(item, meta)
            return official_title.lower(), official_title

        if meta.get("title"):
            return meta.get("title").strip().lower(), meta.get("title").strip()

        clean = re.sub(r"(\.dll|\.Server|ServerMod|Server|\.Client|Client)$", "", item.name, flags=re.I).strip()
        return clean.lower(), item.name

    for item in client_items:
        if item.name.startswith("."):
            continue
        key, display_name = get_mod_group_key(item)
        live_link = CLIENT_MODS_DIR / item.name
        is_enabled = live_link.is_symlink() or live_link.exists()

        if key not in mods_map:
            mods_map[key] = {
                "name": display_name,
                "has_client": True,
                "has_server": False,
                "client_items": [(item, live_link, is_enabled)],
                "server_items": [],
            }
        else:
            mods_map[key]["has_client"] = True
            mods_map[key]["client_items"].append((item, live_link, is_enabled))

    for item in server_items:
        if item.name.startswith("."):
            continue
        key, display_name = get_mod_group_key(item)
        live_link = SERVER_MODS_DIR / item.name
        is_enabled = live_link.is_symlink() or live_link.exists()

        if key not in mods_map:
            mods_map[key] = {
                "name": display_name,
                "has_client": False,
                "has_server": True,
                "client_items": [],
                "server_items": [(item, live_link, is_enabled)],
            }
        else:
            mods_map[key]["has_server"] = True
            mods_map[key]["server_items"].append((item, live_link, is_enabled))

    mods = []
    for key in sorted(list(mods_map.keys())):
        m = mods_map[key]
        c_on = any(p[2] for p in m["client_items"]) if m["has_client"] else False
        s_on = any(p[2] for p in m["server_items"]) if m["has_server"] else False

        if m["has_client"] and m["has_server"]:
            m_type = "Dual (Client + Server)"
            disabled = not (c_on or s_on)
        elif m["has_client"]:
            m_type = "Client (BepInEx)"
            disabled = not c_on
        else:
            m_type = "Server (user/mods)"
            disabled = not s_on

        m["type"] = m_type
        m["disabled"] = disabled

        first_client = m["client_items"][0][0] if m["client_items"] else None
        first_server = m["server_items"][0][0] if m["server_items"] else None

        m["client_staged"] = first_client
        m["server_staged"] = first_server
        m["staged_path"] = first_client or first_server
        m["live_path"] = (m["client_items"][0][1] if m["client_items"] else None) or (
            m["server_items"][0][1] if m["server_items"] else None
        )
        mods.append(m)

    self.all_installed_mods = mods
    self.filter_installed_mods(self.installed_search.text())

    if hasattr(self, "remote_mods") and self.remote_mods and hasattr(self, "table_browse"):
        self.render_browse_catalog(self.remote_mods)

    if hasattr(self, "list_presets") and self.list_presets.currentItem():
        self.on_preset_selected()

    if hasattr(self, "list_presets") and self.list_presets.currentItem():
        self.on_preset_selected()


def render_installed_mods(self, mods):
    self.table_mods.setSortingEnabled(False)
    self.table_mods.setRowCount(0)
    unknown_fika_mods = []

    for mod in mods:
        row = self.table_mods.rowCount()
        self.table_mods.insertRow(row)
        self.table_mods.setRowHeight(row, 40)

        status_str = "❌ Disabled" if mod["disabled"] else "✅ Enabled"
        item_status = QTableWidgetItem(status_str)
        item_status.setForeground(QColor("#f38ba8") if mod["disabled"] else QColor("#a6e3a1"))
        self.table_mods.setItem(row, 0, item_status)

        item_name = QTableWidgetItem(mod["name"])
        item_name.setData(Qt.UserRole, mod)
        self.table_mods.setItem(row, 1, item_name)

        # Metadata resolution for Version & Fika
        meta = load_mod_meta(mod["staged_path"]) or {}
        ver_str = meta.get("version")
        if not ver_str and mod.get("has_server") and mod.get("server_staged"):
            server_meta = load_mod_meta(mod["server_staged"]) or {}
            ver_str = server_meta.get("version")

        if not ver_str:
            matched = find_best_catalog_match_global(mod["name"])
            if matched:
                ver_str = matched.get("version")
        if not ver_str:
            ver_str = "1.0.0"

        display_ver = f"v{ver_str}" if not str(ver_str).startswith("v") else str(ver_str)
        item_ver = QTableWidgetItem(display_ver)
        item_ver.setForeground(QColor("#fab387"))
        self.table_mods.setItem(row, 2, item_ver)

        self.table_mods.setItem(row, 3, QTableWidgetItem(mod["type"]))

        # Fika status
        f_stat = meta.get("fika_status")

        if not f_stat and mod.get("has_server") and mod.get("server_staged"):
            server_meta = load_mod_meta(mod["server_staged"]) or {}
            f_stat = server_meta.get("fika_status")

        if not f_stat or f_stat == "Unknown":
            matched = find_best_catalog_match_global(mod["name"])
            if matched and matched.get("fika_status") and matched.get("fika_status") != "Unknown":
                f_stat = matched.get("fika_status")
                meta["fika_status"] = f_stat
                if mod.get("client_staged"):
                    save_mod_meta(mod["client_staged"], meta)
                if mod.get("server_staged"):
                    save_mod_meta(mod["server_staged"], meta)
            else:
                unknown_fika_mods.append(mod)

        if not f_stat:
            f_stat = "Unknown"

        if "Compatible" in f_stat or f_stat == "Yes":
            item_fika = QTableWidgetItem("🟢 Compatible")
            item_fika.setForeground(QColor("#a6e3a1"))
        elif "Incompatible" in f_stat or f_stat == "No":
            item_fika = QTableWidgetItem("🔴 Incompatible")
            item_fika.setForeground(QColor("#f38ba8"))
        else:
            item_fika = QTableWidgetItem("🟡 Unknown")
            item_fika.setForeground(QColor("#fab387"))

        self.table_mods.setItem(row, 4, item_fika)

        # Author column as underlined hyperlink
        author_str = meta.get("author")
        if not author_str or author_str == "Community":
            matched = find_best_catalog_match_global(mod["name"])
            if matched and matched.get("creator"):
                author_str = matched.get("creator")
        if not author_str:
            author_str = "Community"

        item_author = QTableWidgetItem(f"by {author_str}")
        font_author = item_author.font()
        font_author.setUnderline(True)
        item_author.setFont(font_author)
        item_author.setForeground(QColor("#89b4fa"))
        item_author.setToolTip(f"Open {author_str}'s profile on sp-mod.com")
        self.table_mods.setItem(row, 5, item_author)

        # Action buttons widget
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(2, 2, 2, 2)
        action_layout.setSpacing(4)

        if not mod["disabled"]:
            btn_toggle = QPushButton("Disable")
            btn_toggle.setMinimumWidth(75)
            btn_toggle.setStyleSheet("""
                QPushButton { background-color: #3b2d24; color: #fab387; border: 1px solid #543f31; font-weight: bold; border-radius: 4px; }
                QPushButton:hover { background-color: #4a392e; border-color: #fab387; }
            """)
        else:
            btn_toggle = QPushButton("Enable")
            btn_toggle.setMinimumWidth(75)
            btn_toggle.setStyleSheet("""
                QPushButton { background-color: #27392b; color: #a6e3a1; border: 1px solid #36503c; font-weight: bold; border-radius: 4px; }
                QPushButton:hover { background-color: #314a38; border-color: #a6e3a1; }
            """)

        btn_toggle.clicked.connect(lambda _, m=mod: self.toggle_mod(m))
        action_layout.addWidget(btn_toggle)

        btn_del = QPushButton("Delete")
        btn_del.setMinimumWidth(70)
        btn_del.setStyleSheet("""
            QPushButton { background-color: #3a232e; color: #f38ba8; border: 1px solid #542f3e; font-weight: bold; border-radius: 4px; }
            QPushButton:hover { background-color: #4a2c3b; border-color: #f38ba8; }
        """)
        btn_del.clicked.connect(lambda _, m=mod: self.delete_mod(m))
        action_layout.addWidget(btn_del)

        self.table_mods.setCellWidget(row, 6, action_widget)

    self.table_mods.setSortingEnabled(True)
    self.update_bulk_actions_bar()

    if unknown_fika_mods:
        self.fika_sync_thread = FikaSyncThread(unknown_fika_mods, self)
        self.fika_sync_thread.updated.connect(self.on_fika_updated)
        self.fika_sync_thread.start()


def on_fika_updated(self, mod_name, fika_status):
    for row in range(self.table_mods.rowCount()):
        item_name = self.table_mods.item(row, 1)
        if item_name and item_name.text().lower() == mod_name.lower():
            if "Compatible" in fika_status or fika_status == "Yes":
                item_fika = QTableWidgetItem("🟢 Compatible")
                item_fika.setForeground(QColor("#a6e3a1"))
            elif "Incompatible" in fika_status or fika_status == "No":
                item_fika = QTableWidgetItem("🔴 Incompatible")
                item_fika.setForeground(QColor("#f38ba8"))
            else:
                item_fika = QTableWidgetItem("🟡 Unknown")
                item_fika.setForeground(QColor("#fab387"))
            self.table_mods.setItem(row, 4, item_fika)


def on_installed_table_cell_clicked(self, row, col):
    if col == 5:
        mod_item = self.table_mods.item(row, 1)
        if mod_item:
            mod = mod_item.data(Qt.UserRole)
            if mod:
                url = resolve_author_profile_url(mod)
                QDesktopServices.openUrl(QUrl(url))


def show_installed_table_context_menu(self, pos):
    item = self.table_mods.itemAt(pos)
    if not item:
        return
    row = item.row()
    mod_item = self.table_mods.item(row, 1)
    if not mod_item:
        return
    mod = mod_item.data(Qt.UserRole)
    if not mod:
        return

    menu = QMenu(self)
    menu.setStyleSheet("""
        QMenu { background-color: #1e1e2e; color: #cdd6f4; border: 1px solid #45475a; border-radius: 8px; padding: 6px; }
        QMenu::item { padding: 8px 24px; border-radius: 4px; font-weight: 500; }
        QMenu::item:selected { background-color: #313244; color: #89b4fa; }
        QMenu::separator { height: 1px; background-color: #313244; margin: 4px 0px; }
    """)

    act_open_folder = menu.addAction("📁 Open Folder in File Manager")
    act_open_web = menu.addAction("🔗 Open Web Page on sp-mod.com")

    meta = load_mod_meta(mod["staged_path"]) or {}
    author_str = meta.get("author")
    if not author_str or author_str == "Community":
        matched = find_best_catalog_match_global(mod["name"])
        if matched:
            author_str = matched.get("creator")

    act_author_search = None
    if author_str and author_str != "Community":
        act_author_search = menu.addAction(f"👤 Open {author_str}'s Profile on sp-mod.com")

    menu.addSeparator()

    is_disabled = mod.get("disabled", False)
    act_toggle = menu.addAction("⚡ Enable Mod" if is_disabled else "⏸ Disable Mod")
    act_check_upd = menu.addAction("🔄 Check for Updates")
    menu.addSeparator()

    act_copy_path = menu.addAction("📋 Copy Path to Clipboard")
    menu.addSeparator()

    act_delete = menu.addAction("🗑 Delete Mod Package")

    global_pos = self.table_mods.viewport().mapToGlobal(pos)
    action = menu.exec(global_pos)
    if not action:
        return

    if action == act_open_folder:
        staged_p = mod.get("staged_path")
        if staged_p and staged_p.exists():
            folder_to_open = staged_p if staged_p.is_dir() else staged_p.parent
            try:
                subprocess.Popen(["xdg-open", str(folder_to_open)])
            except Exception as e:
                QMessageBox.warning(self, "Open Folder Error", f"Could not open file manager: {e}")
    elif action == act_open_web:
        matched = find_best_catalog_match_global(mod["name"])
        link = meta.get("link") or (matched.get("link") if matched else None)
        if not link:
            query = urllib.parse.quote(mod["name"])
            link = f"https://sp-mod.com/mods?query={query}"
        QDesktopServices.openUrl(QUrl(link))
    elif act_author_search and action == act_author_search:
        url = resolve_author_profile_url(mod)
        QDesktopServices.openUrl(QUrl(url))
    elif action == act_toggle:
        self.toggle_mod(mod)
    elif action == act_check_upd:
        self.check_installed_mod_updates()
    elif action == act_copy_path:
        staged_p = mod.get("staged_path")
        if staged_p:
            QApplication.clipboard().setText(str(staged_p))
            QMessageBox.information(self, "Copied Path", f"📋 Path copied to clipboard:\n\n{staged_p}")
    elif action == act_delete:
        self.delete_mod(mod)


def check_installed_mod_updates(self, *args):
    if not hasattr(self, "all_installed_mods") or not self.all_installed_mods:
        self.load_installed_mods()

    updates = []
    for mod in getattr(self, "all_installed_mods", []):
        staged_p = mod.get("staged_path")
        meta = load_mod_meta(staged_p) if staged_p else {}
        matched = find_best_catalog_match_global(mod["name"])

        curr_ver = meta.get("version") if meta else "1.0.0"
        latest_ver = matched.get("version") if matched else None

        if matched and latest_ver and is_version_newer(latest_ver, curr_ver):
            updates.append(
                {
                    "mod": mod,
                    "current_ver": curr_ver,
                    "latest_ver": latest_ver,
                    "title": matched.get("title", mod["name"]),
                    "download_url": matched.get("download_url", ""),
                    "link": matched.get("link", ""),
                }
            )

    if not updates:
        QMessageBox.information(
            self,
            "Up to Date!",
            "✅ <b>All installed mods are up to date!</b><br>No newer versions were found on sp-mod.com.",
        )
        return

    upd_list = "\n".join(
        f"• <b>{html.escape(u['title'])}</b>: v{u['current_ver']} → <b style='color:#a6e3a1;'>v{u['latest_ver']}</b>"
        for u in updates[:15]
    )
    extra = f"\n...and {len(updates) - 15} more" if len(updates) > 15 else ""

    reply = QMessageBox.question(
        self,
        "Mod Updates Available",
        f"🎉 <b>{len(updates)} mod update(s) available</b>:\n\n"
        f"{upd_list}{extra}\n\n"
        f"Would you like to download and install all available updates now?",
        QMessageBox.Yes | QMessageBox.No,
    )
    if reply == QMessageBox.Yes:
        update_mods_queue = [
            {"title": u["title"], "download_url": u["download_url"], "link": u["link"], "version": u["latest_ver"]}
            for u in updates
            if u["download_url"]
        ]
        if update_mods_queue:
            self.start_dependency_queue_download(update_mods_queue, None)


def update_bulk_actions_bar(self):
    selected_mods = self.get_selected_installed_mods()
    cnt = len(selected_mods)
    if hasattr(self, "lbl_selected_count"):
        total_pkgs = len(getattr(self, "all_installed_mods", []))
        total_files = sum(
            len(m.get("client_items", [])) + len(m.get("server_items", []))
            for m in getattr(self, "all_installed_mods", [])
        )
        if cnt > 0:
            selected_files = sum(len(m.get("client_items", [])) + len(m.get("server_items", [])) for m in selected_mods)
            self.lbl_selected_count.setText(
                f"<b>{cnt}</b> of <b>{total_pkgs}</b> Mod Packages selected ({selected_files} component files)"
            )
        else:
            self.lbl_selected_count.setText(
                f"<b>{total_pkgs}</b> Mod Packages installed (<b>{total_files}</b> component files)"
            )
    if hasattr(self, "btn_bulk_enable"):
        self.btn_bulk_enable.setEnabled(cnt > 0)
        self.btn_bulk_disable.setEnabled(cnt > 0)
        self.btn_bulk_delete.setEnabled(cnt > 0)


def get_selected_installed_mods(self):
    rows = set(item.row() for item in self.table_mods.selectedItems())
    selected = []
    for r in sorted(list(rows)):
        item = self.table_mods.item(r, 1)
        if item:
            mod_data = item.data(Qt.UserRole)
            if mod_data:
                selected.append(mod_data)
    return selected


def select_all_installed_mods(self):
    self.table_mods.selectAll()


def deselect_all_installed_mods(self):
    self.table_mods.clearSelection()


def bulk_enable_selected(self):
    selected = self.get_selected_installed_mods()
    if not selected:
        return

    enabled_count = 0
    for mod in selected:
        if mod.get("disabled", False):
            client_items = mod.get("client_items", [])
            server_items = mod.get("server_items", [])
            for item, live_link, _ in client_items:
                if live_link.is_symlink() or live_link.exists():
                    if live_link.is_symlink() or not live_link.is_dir():
                        live_link.unlink()
                    else:
                        shutil.rmtree(live_link)
                os.symlink(str(item), str(live_link))
            for item, live_link, _ in server_items:
                if live_link.is_symlink() or live_link.exists():
                    if live_link.is_symlink() or not live_link.is_dir():
                        live_link.unlink()
                    else:
                        shutil.rmtree(live_link)
                os.symlink(str(item), str(live_link))

            enabled_count += 1

    self.load_installed_mods()
    QMessageBox.information(self, "Bulk Enable Complete", f"▶ Enabled <b>{enabled_count}</b> mod package(s)!")


def bulk_disable_selected(self):
    selected = self.get_selected_installed_mods()
    if not selected:
        return

    disabled_count = 0
    for mod in selected:
        if not mod.get("disabled", False):
            client_items = mod.get("client_items", [])
            server_items = mod.get("server_items", [])
            for _, live_link, _ in client_items:
                if live_link.is_symlink() or live_link.exists():
                    if live_link.is_symlink() or not live_link.is_dir():
                        live_link.unlink()
                    else:
                        shutil.rmtree(live_link)
            for _, live_link, _ in server_items:
                if live_link.is_symlink() or live_link.exists():
                    if live_link.is_symlink() or not live_link.is_dir():
                        live_link.unlink()
                    else:
                        shutil.rmtree(live_link)

            disabled_count += 1

    self.load_installed_mods()
    QMessageBox.information(self, "Bulk Disable Complete", f"⏸ Disabled <b>{disabled_count}</b> mod package(s)!")


def bulk_delete_selected(self):
    selected = self.get_selected_installed_mods()
    if not selected:
        return

    names = "\n".join(f"• {m['name']}" for m in selected[:15])
    extra = f"\n...and {len(selected) - 15} more" if len(selected) > 15 else ""
    reply = QMessageBox.question(
        self,
        "Delete Selected Mods?",
        f"Are you sure you want to PERMANENTLY delete <b>{len(selected)} selected mod package(s)</b>?\n\n"
        f"{names}{extra}\n\n"
        f"This will delete all staged files and live symlinks.",
        QMessageBox.Yes | QMessageBox.No,
    )
    if reply == QMessageBox.Yes:
        for mod in selected:
            purge_mod_files_and_symlinks(mod)

        self.load_installed_mods()
        QMessageBox.information(self, "Bulk Delete Complete", f"🗑 Deleted <b>{len(selected)}</b> mod package(s)!")


def filter_installed_mods(self, text):
    query = text.lower().strip()
    filtered = [m for m in self.all_installed_mods if query in m["name"].lower() or query in m["type"].lower()]
    self.render_installed_mods(filtered)


def toggle_mod(self, mod):
    try:
        if mod["disabled"]:
            mod_url = None
            matched = next(
                (
                    m
                    for m in self.remote_mods
                    if m["title"].lower() in mod["name"].lower() or mod["name"].lower() in m["title"].lower()
                ),
                None,
            )
            if matched:
                mod_url = matched.get("link")

            if mod_url:
                deps = fetch_mod_dependencies_sync({"link": mod_url})
                staged_disabled_deps = [d for d in deps if d.get("status") == "STAGED_DISABLED"]
                if staged_disabled_deps:
                    dep_names = "\n".join(f"• {d['title']}" for d in staged_disabled_deps)
                    reply = QMessageBox.question(
                        self,
                        "Enable Required Dependencies?",
                        f"<b>{mod['name']}</b> requires the following dependency mod(s) which are currently disabled in your Stash:\n\n"
                        f"{dep_names}\n\n"
                        f"Would you like to enable these dependencies as well?",
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    )
                    if reply == QMessageBox.Cancel:
                        return
                    if reply == QMessageBox.Yes:
                        for d in staged_disabled_deps:
                            dep_p = d["path"]
                            is_srv = "server" in str(dep_p).lower()
                            link_p = (SERVER_MODS_DIR if is_srv else CLIENT_MODS_DIR) / dep_p.name
                            if link_p.is_symlink() or link_p.exists():
                                if link_p.is_symlink() or not link_p.is_dir():
                                    link_p.unlink()
                                else:
                                    shutil.rmtree(link_p)
                            os.symlink(str(dep_p), str(link_p))

            client_items = mod.get("client_items", [])
            server_items = mod.get("server_items", [])

            for item, live_link, _ in client_items:
                create_relative_symlink(item, live_link)

            for item, live_link, _ in server_items:
                create_relative_symlink(item, live_link)

        else:
            client_items = mod.get("client_items", [])
            server_items = mod.get("server_items", [])

            for _, live_link, _ in client_items:
                if live_link.is_symlink() or live_link.exists():
                    if live_link.is_symlink() or not live_link.is_dir():
                        live_link.unlink()
                    else:
                        shutil.rmtree(live_link)

            for _, live_link, _ in server_items:
                if live_link.is_symlink() or live_link.exists():
                    if live_link.is_symlink() or not live_link.is_dir():
                        live_link.unlink()
                    else:
                        shutil.rmtree(live_link)

        self.load_installed_mods()
    except Exception as e:
        QMessageBox.critical(self, "Error", f"Failed to toggle mod: {e}")


def audit_installed_dependencies(self):
    if not hasattr(self, "all_installed_mods") or not self.all_installed_mods:
        QMessageBox.information(self, "Audit Dependencies", "No installed mods found to audit.")
        return

    progress = QProgressDialog(
        "🔍 Auditing dependencies for installed mods...", "Cancel", 0, len(self.all_installed_mods), self
    )
    progress.setWindowModality(Qt.WindowModal)
    progress.show()

    issues = []

    for i, mod in enumerate(self.all_installed_mods):
        if progress.wasCanceled():
            break
        progress.setValue(i)
        progress.setLabelText(f"🔍 Auditing ({i + 1}/{len(self.all_installed_mods)}): {mod['name']}...")
        QApplication.processEvents()

        matched = next(
            (
                m
                for m in self.remote_mods
                if m["title"].lower() in mod["name"].lower() or mod["name"].lower() in m["title"].lower()
            ),
            None,
        )
        if matched:
            deps = fetch_mod_dependencies_sync(matched)
            missing = [d for d in deps if d.get("status") == "MISSING"]
            disabled = [d for d in deps if d.get("status") == "STAGED_DISABLED"]
            if missing or disabled:
                issues.append({"mod_name": mod["name"], "mod_info": matched, "missing": missing, "disabled": disabled})

    progress.setValue(len(self.all_installed_mods))

    if not issues:
        QMessageBox.information(
            self, "Audit Complete", "✅ All installed mods have their required dependencies installed and enabled!"
        )
        return

    self.show_audit_issues_dialog(issues)


def show_audit_issues_dialog(self, issues):
    msg = f"<b>Found dependency issues for {len(issues)} installed mod(s):</b><br/><br/>"
    all_missing_to_download = []
    all_disabled_to_enable = []

    for item in issues:
        msg += f"<b>• {item['mod_name']}</b>:<br/>"
        for d in item["disabled"]:
            msg += f"  - <span style='color:#fab387;'>Disabled in Stash:</span> {d['title']}<br/>"
            all_disabled_to_enable.append(d)
        for m in item["missing"]:
            msg += f"  - <span style='color:#f38ba8;'>Missing:</span> {m['title']}<br/>"
            all_missing_to_download.append(m)
        msg += "<br/>"

    msg += "Would you like to automatically enable disabled Stash dependencies and download missing dependencies?"

    reply = QMessageBox.question(self, "Dependency Audit Results", msg, QMessageBox.Yes | QMessageBox.No)

    if reply == QMessageBox.Yes:
        for d in all_disabled_to_enable:
            dep_p = d["path"]
            is_srv = "server" in str(dep_p).lower()
            link_p = (SERVER_MODS_DIR if is_srv else CLIENT_MODS_DIR) / dep_p.name
            if link_p.is_symlink() or link_p.exists():
                if link_p.is_symlink() or not link_p.is_dir():
                    link_p.unlink()
                else:
                    shutil.rmtree(link_p)
            os.symlink(str(dep_p), str(link_p))

        if all_missing_to_download:
            self.start_dependency_queue_download(all_missing_to_download, None)

        self.load_installed_mods()
        QMessageBox.information(self, "Audit Auto-Fix", "✅ Dependency auto-fix process completed!")


def delete_mod(self, mod):
    reply = QMessageBox.question(
        self,
        "Confirm Delete",
        f"Are you sure you want to permanently delete '{mod['name']}' from your staged library?",
        QMessageBox.Yes | QMessageBox.No,
    )
    if reply == QMessageBox.Yes:
        try:
            purge_mod_files_and_symlinks(mod)
            self.load_installed_mods()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete mod: {e}")
