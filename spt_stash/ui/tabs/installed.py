#!/usr/bin/env python3
"""SPT Stash — Installed Mods tab (V4 layout matching reference mockup)."""

import html
import re
import urllib.parse
import urllib.request

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ... import paths
from ...catalog.dependencies import fetch_mod_dependencies_sync
from ...catalog.matching import find_best_catalog_match_global, resolve_author_profile_url
from ...catalog.workers import ModDetailFetcherThread
from ...staging.links import (
    adopt_unmanaged_mods,
    create_relative_symlink,
    purge_mod_files_and_symlinks,
    remove_path,
)
from ...staging.metadata import load_mod_meta, save_mod_meta
from ...staging.workers import FikaSyncThread
from ...system import host
from ...version import is_version_newer
from ..theme import ACCENT, BG, BORDER, DANGER, DISABLED_TEXT, SUCCESS, SURFACE, SURFACE_2, TEXT, TEXT_MUTED, WARNING
from ..widgets import (
    CheckBox,
    ClickableLabel,
    LinkButton,
    RemoteImageTextBrowser,
    SearchField,
    ToggleSwitch,
    _nav_pixmap,
)


def setup_installed_tab(self):
    layout = QVBoxLayout(self.tab_installed)
    layout.setContentsMargins(22, 16, 22, 16)
    layout.setSpacing(12)

    self.current_filter_mode = "all"
    self.selected_mod_keys = set()

    #  Top Row: Header & Action Tools
    top_row = QHBoxLayout()
    top_row.setSpacing(10)

    lbl_title = QLabel("Installed Mods")
    lbl_title.setStyleSheet("font-size: 18px; font-weight: 700; letter-spacing: -0.02em;")
    top_row.addWidget(lbl_title)

    self.lbl_installed_summary = QLabel("0 packages · 0 enabled")
    self.lbl_installed_summary.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; margin-left: 4px;")
    top_row.addWidget(self.lbl_installed_summary)

    top_row.addStretch()

    btn_updates = QPushButton("Check Updates")
    btn_updates.setProperty("size", "sm")
    btn_updates.setProperty("role", "ghost")
    btn_updates.clicked.connect(lambda: self.check_installed_mod_updates())
    top_row.addWidget(btn_updates)

    btn_audit = QPushButton("Audit Dependencies")
    btn_audit.setProperty("size", "sm")
    btn_audit.setProperty("role", "ghost")
    btn_audit.clicked.connect(lambda: self.audit_installed_dependencies())
    top_row.addWidget(btn_audit)

    layout.addLayout(top_row)

    #  Toolbar: Search + Filter Chips + Import/Export
    toolbar = QHBoxLayout()
    toolbar.setSpacing(8)

    search_wrap = QHBoxLayout()
    search_wrap.setSpacing(0)
    search_wrap.setContentsMargins(0, 0, 0, 0)

    self.installed_search = SearchField(width=320)
    self.installed_search.textChanged.connect(lambda txt: self.filter_installed_mods(txt))
    search_wrap.addWidget(self.installed_search)

    toolbar.addLayout(search_wrap)

    # Chips
    self.chip_all = QPushButton("All")
    self.chip_all.setProperty("chip", "true")
    self.chip_all.setCheckable(True)
    self.chip_all.setChecked(True)
    self.chip_all.clicked.connect(lambda: self._set_chip_filter("all"))
    toolbar.addWidget(self.chip_all)

    self.chip_enabled = QPushButton("Enabled")
    self.chip_enabled.setProperty("chip", "true")
    self.chip_enabled.setCheckable(True)
    self.chip_enabled.clicked.connect(lambda: self._set_chip_filter("enabled"))
    toolbar.addWidget(self.chip_enabled)

    self.chip_client = QPushButton("Client")
    self.chip_client.setProperty("chip", "true")
    self.chip_client.setCheckable(True)
    self.chip_client.clicked.connect(lambda: self._set_chip_filter("client"))
    toolbar.addWidget(self.chip_client)

    self.chip_server = QPushButton("Server")
    self.chip_server.setProperty("chip", "true")
    self.chip_server.setCheckable(True)
    self.chip_server.clicked.connect(lambda: self._set_chip_filter("server"))
    toolbar.addWidget(self.chip_server)

    self.chip_fika = QPushButton("Fika")
    self.chip_fika.setProperty("chip", "true")
    self.chip_fika.setCheckable(True)
    self.chip_fika.clicked.connect(lambda: self._set_chip_filter("fika"))
    toolbar.addWidget(self.chip_fika)

    toolbar.addStretch()

    btn_export = QPushButton("Export")
    btn_export.setProperty("size", "sm")
    btn_export.setProperty("role", "ghost")
    btn_export.clicked.connect(lambda: self.export_stash_manifest())
    toolbar.addWidget(btn_export)

    btn_import = QPushButton("Import")
    btn_import.setProperty("size", "sm")
    btn_import.setProperty("role", "ghost")
    btn_import.clicked.connect(lambda: self.import_stash_manifest())
    toolbar.addWidget(btn_import)

    btn_refresh = QPushButton("Refresh")
    btn_refresh.setIcon(QIcon(_nav_pixmap("refresh", size=14, color=TEXT_MUTED)))
    btn_refresh.setIconSize(QSize(14, 14))
    btn_refresh.setProperty("size", "sm")
    btn_refresh.setProperty("role", "ghost")
    btn_refresh.setToolTip("Refresh installed mods")
    btn_refresh.clicked.connect(lambda: self.load_installed_mods())
    toolbar.addWidget(btn_refresh)

    layout.addLayout(toolbar)

    self.table_mods = QTableWidget()
    self.table_mods.setObjectName("tableMods")
    self.table_mods.setColumnCount(7)
    self.table_mods.setHorizontalHeaderLabels(["", "ON", "MOD", "VERSION", "TYPE", "FIKA", ""])
    self.table_mods.verticalHeader().setVisible(False)
    self.table_mods.setShowGrid(False)
    self.table_mods.verticalHeader().setDefaultSectionSize(46)
    self.table_mods.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)

    self.table_mods.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
    self.table_mods.setColumnWidth(0, 34)
    self.table_mods.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
    self.table_mods.setColumnWidth(1, 58)
    self.table_mods.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
    self.table_mods.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
    self.table_mods.setColumnWidth(3, 80)
    self.table_mods.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
    self.table_mods.setColumnWidth(4, 80)
    self.table_mods.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
    self.table_mods.setColumnWidth(5, 105)
    self.table_mods.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)
    self.table_mods.setColumnWidth(6, 90)

    self.table_mods.setSelectionMode(QAbstractItemView.NoSelection)
    self.table_mods.setContextMenuPolicy(Qt.CustomContextMenu)
    self.table_mods.customContextMenuRequested.connect(lambda pos: self.show_installed_table_context_menu(pos))
    self.table_mods.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    self.table_mods.verticalHeader().setDefaultSectionSize(46)
    self.table_mods.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)

    layout.addWidget(self.table_mods)
    layout.setStretchFactor(self.table_mods, 1)

    # Floating detail popup (shown when a mod name is clicked)
    self._installed_detail_popup = QFrame(self.tab_installed)
    self._installed_detail_popup.setObjectName("modDetailPopup")
    self._installed_detail_popup.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
    self._installed_detail_popup.setStyleSheet(f"""
        QFrame#modDetailPopup {{
            background-color: {SURFACE};
            border: 1px solid {BORDER};
            border-radius: 12px;
        }}
        QFrame#modDetailPopup QLabel {{
            background: transparent;
            border: none;
        }}
    """)
    self._installed_detail_popup.setFixedSize(420, 520)
    popup_layout = QVBoxLayout(self._installed_detail_popup)
    popup_layout.setContentsMargins(12, 12, 12, 12)
    popup_layout.setSpacing(0)

    self.installed_detail = RemoteImageTextBrowser(self._installed_detail_popup)
    self.installed_detail.setOpenExternalLinks(True)
    self.installed_detail.setStyleSheet(
        f"background-color: transparent; border: none; color: {TEXT}; padding: 0px;"
    )
    popup_layout.addWidget(self.installed_detail)

    #  Bulk Actions Bar
    bulk_bar = QFrame()
    bulk_bar.setObjectName("bulkBar")
    bulk_layout = QHBoxLayout(bulk_bar)
    bulk_layout.setContentsMargins(14, 8, 14, 8)
    bulk_layout.setSpacing(12)

    self.lbl_bulk_count = QLabel("0 of 0 selected")
    self.lbl_bulk_count.setObjectName("bulkCount")
    bulk_layout.addWidget(self.lbl_bulk_count)

    btn_select_all = QPushButton("Select all")
    btn_select_all.setProperty("role", "ghost")
    btn_select_all.setProperty("size", "sm")
    btn_select_all.clicked.connect(lambda: self.select_all_installed_mods())
    bulk_layout.addWidget(btn_select_all)

    btn_clear = QPushButton("Clear")
    btn_clear.setProperty("role", "ghost")
    btn_clear.setProperty("size", "sm")
    btn_clear.clicked.connect(lambda: self.deselect_all_installed_mods())
    bulk_layout.addWidget(btn_clear)

    bulk_layout.addStretch()

    self.btn_bulk_enable = QPushButton("Enable Selected")
    self.btn_bulk_enable.setProperty("role", "success")
    self.btn_bulk_enable.setProperty("size", "sm")
    self.btn_bulk_enable.clicked.connect(lambda: self.bulk_enable_selected())
    self.btn_bulk_enable.setEnabled(False)
    bulk_layout.addWidget(self.btn_bulk_enable)

    self.btn_bulk_disable = QPushButton("Disable Selected")
    self.btn_bulk_disable.setProperty("size", "sm")
    self.btn_bulk_disable.clicked.connect(lambda: self.bulk_disable_selected())
    self.btn_bulk_disable.setEnabled(False)
    bulk_layout.addWidget(self.btn_bulk_disable)

    self.btn_bulk_delete = QPushButton("Delete Selected")
    self.btn_bulk_delete.setProperty("role", "danger")
    self.btn_bulk_delete.setProperty("size", "sm")
    self.btn_bulk_delete.clicked.connect(lambda: self.bulk_delete_selected())
    self.btn_bulk_delete.setEnabled(False)
    bulk_layout.addWidget(self.btn_bulk_delete)

    layout.addWidget(bulk_bar)

    self.load_installed_mods()


def _set_chip_filter(self, mode):
    chips = ["all", "enabled", "client", "server", "fika"]
    for c in chips:
        btn = getattr(self, f"chip_{c}", None)
        if btn:
            btn.setChecked(c == mode)
    self.current_filter_mode = mode
    self.filter_installed_mods(self.installed_search.text())


def _guess_version(name):
    """Best-effort version from a folder name like 'AmandsSense-3.1.0'; '' when none is present."""
    m = re.search(r"(?<![\w.])v?(\d+(?:\.\d+)+)", name)
    return m.group(1) if m else ""


def load_installed_mods(self):
    self.table_mods.setRowCount(0)
    adopt_unmanaged_mods(paths.STAGED_CLIENT, paths.CLIENT_MODS_DIR)
    adopt_unmanaged_mods(paths.STAGED_SERVER, paths.SERVER_MODS_DIR)
    mods_map = {}

    client_items = list(paths.STAGED_CLIENT.iterdir()) if paths.STAGED_CLIENT.exists() else []
    server_items = list(paths.STAGED_SERVER.iterdir()) if paths.STAGED_SERVER.exists() else []

    def get_mod_group_key(item):
        meta = load_mod_meta(item) or {}
        matched = find_best_catalog_match_global(item.name)

        if matched and matched.get("title"):
            official_title = matched.get("title").strip()
            if meta.get("title") != official_title or not meta.get("link"):
                meta["title"] = official_title
                meta["link"] = matched.get("link", meta.get("link", ""))
                meta["author"] = matched.get("creator", meta.get("author", ""))
                # Never stamp the catalog's *latest* version as installed — that hides real updates.
                meta["version"] = meta.get("version") or _guess_version(item.name)
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
        live_link = paths.CLIENT_MODS_DIR / item.name
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
        live_link = paths.SERVER_MODS_DIR / item.name
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
            m_type = "Client/Server"
            disabled = not (c_on or s_on)
        elif m["has_client"]:
            m_type = "Client"
            disabled = not c_on
        else:
            m_type = "Server"
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

    if getattr(self, "remote_mods", None) and hasattr(self, "list_remote"):
        self.filter_remote_mods()

    if hasattr(self, "list_presets") and self.list_presets.currentItem():
        self.on_preset_selected()


def render_installed_mods(self, mods):
    self.table_mods.setRowCount(0)
    unknown_fika_mods = []

    # Update dynamic summary header label
    total_pkgs = len(getattr(self, "all_installed_mods", []))
    enabled_pkgs = sum(1 for m in getattr(self, "all_installed_mods", []) if not m.get("disabled", False))
    if hasattr(self, "lbl_installed_summary"):
        self.lbl_installed_summary.setText(f"{total_pkgs} packages · {enabled_pkgs} enabled")

    self.row_checkboxes = []

    for mod in mods:
        row = self.table_mods.rowCount()
        self.table_mods.insertRow(row)
        self.table_mods.setRowHeight(row, 48)

        # Col 0: Selection Checkbox (for bulk actions)
        chk_sel_widget = QWidget()
        chk_sel_layout = QHBoxLayout(chk_sel_widget)
        chk_sel_layout.setContentsMargins(6, 0, 0, 0)
        chk_sel_layout.setAlignment(Qt.AlignCenter)
        chk_sel = CheckBox()
        chk_sel.setChecked(mod["name"] in getattr(self, "selected_mod_keys", set()))
        chk_sel.toggled.connect(lambda checked, m=mod: self._on_mod_row_checked(m, checked))
        chk_sel_layout.addWidget(chk_sel)
        self.table_mods.setCellWidget(row, 0, chk_sel_widget)
        self.row_checkboxes.append((chk_sel, mod))

        # Col 1: Toggle Switch
        chk_widget = QWidget()
        chk_layout = QHBoxLayout(chk_widget)
        chk_layout.setContentsMargins(4, 0, 4, 0)
        chk_layout.setAlignment(Qt.AlignCenter)
        chk = ToggleSwitch()
        chk.setChecked(not mod["disabled"])
        chk.setToolTip("Toggle mod on/off" if not mod["disabled"] else "Enable mod")
        chk.toggled.connect(lambda checked, m=mod: self.toggle_mod(m))
        chk_layout.addWidget(chk)
        self.table_mods.setCellWidget(row, 1, chk_widget)

        # Col 2: Mod Name + Author (two lines)
        meta = load_mod_meta(mod["staged_path"]) or {}
        author_str = meta.get("author")
        if not author_str or author_str == "Community":
            matched = find_best_catalog_match_global(mod["name"])
            if matched and matched.get("creator"):
                author_str = matched.get("creator")
        if not author_str:
            author_str = "Community"

        name_widget = QWidget()
        name_layout = QVBoxLayout(name_widget)
        name_layout.setContentsMargins(4, 4, 4, 4)
        name_layout.setSpacing(1)

        lbl_name = ClickableLabel(mod["name"])
        if mod["disabled"]:
            lbl_name.setStyleSheet(f"font-weight: 600; font-size: 13px; color: {DISABLED_TEXT};")
        else:
            lbl_name.setStyleSheet(f"font-weight: 600; font-size: 13px; color: {TEXT};")
        lbl_name.clicked.connect(lambda _m=mod: self.show_installed_mod_detail(_m))
        name_layout.addWidget(lbl_name)

        if author_str and author_str != "Community":
            if mod["disabled"]:
                lbl_author = LinkButton(f"by {author_str}", color=TEXT_MUTED, underline=False)
            else:
                lbl_author = LinkButton(f"by {author_str}", color=ACCENT, underline=True)
            lbl_author.setToolTip(f"Open {author_str}'s profile on sp-mod.com")
            lbl_author.clicked.connect(lambda _m=mod: self.open_author_profile(_m))
            name_layout.addWidget(lbl_author)
        name_layout.addStretch()

        hidden_item = QTableWidgetItem(mod["name"])
        hidden_item.setData(Qt.UserRole, mod)
        self.table_mods.setItem(row, 2, hidden_item)
        self.table_mods.setCellWidget(row, 2, name_widget)

        # Col 3: Version
        ver_str = meta.get("version")
        if not ver_str and mod.get("has_server") and mod.get("server_staged"):
            server_meta = load_mod_meta(mod["server_staged"]) or {}
            ver_str = server_meta.get("version")
        if not ver_str:
            ver_str = "unknown"

        display_ver = f"v{ver_str}" if str(ver_str)[:1].isdigit() else str(ver_str)
        item_ver = QTableWidgetItem(display_ver)
        item_ver.setForeground(QColor(TEXT_MUTED))
        item_ver.setTextAlignment(Qt.AlignCenter)
        self.table_mods.setItem(row, 3, item_ver)

        # Col 4: Type
        item_type = QTableWidgetItem(mod["type"])
        item_type.setForeground(QColor(TEXT_MUTED))
        item_type.setTextAlignment(Qt.AlignCenter)
        self.table_mods.setItem(row, 4, item_type)

        # Col 5: Fika Status Pill
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

        fika_widget = QWidget()
        fika_layout = QHBoxLayout(fika_widget)
        fika_layout.setContentsMargins(2, 0, 2, 0)
        fika_layout.setAlignment(Qt.AlignCenter)

        lbl_fika_pill = QLabel()
        lbl_fika_pill.setProperty("pill", "true")
        if "Compatible" in f_stat or f_stat == "Yes":
            lbl_fika_pill.setText("Compatible")
            lbl_fika_pill.setProperty("pill", "success")
        elif "Incompatible" in f_stat or f_stat == "No":
            lbl_fika_pill.setText("Issues")
            lbl_fika_pill.setProperty("pill", "warn")
        else:
            lbl_fika_pill.setText("Unknown")
            lbl_fika_pill.setProperty("pill", "muted")

        fika_layout.addWidget(lbl_fika_pill)
        self.table_mods.setCellWidget(row, 5, fika_widget)

        # Col 6: Action Buttons
        actions_widget = QWidget()
        actions_layout = QHBoxLayout(actions_widget)
        actions_layout.setContentsMargins(2, 2, 2, 2)
        actions_layout.setSpacing(4)
        actions_layout.setAlignment(Qt.AlignCenter)

        btn_folder = QPushButton()
        btn_folder.setIcon(QIcon(_nav_pixmap("folder", size=14, color=TEXT_MUTED)))
        btn_folder.setIconSize(QSize(14, 14))
        btn_folder.setToolTip("Open mod folder in File Manager")
        btn_folder.setProperty("iconBtn", "true")
        btn_folder.clicked.connect(lambda _, m=mod: self.open_mod_folder(m))
        actions_layout.addWidget(btn_folder)

        btn_web = QPushButton()
        btn_web.setIcon(QIcon(_nav_pixmap("external", size=14, color=TEXT_MUTED)))
        btn_web.setIconSize(QSize(14, 14))
        btn_web.setToolTip("View on sp-mod.com Forge")
        btn_web.setProperty("iconBtn", "true")
        btn_web.clicked.connect(lambda _, m=mod: self.open_mod_web(m))
        actions_layout.addWidget(btn_web)

        btn_del = QPushButton()
        btn_del.setIcon(QIcon(_nav_pixmap("trash", size=14, color=DANGER)))
        btn_del.setIconSize(QSize(14, 14))
        btn_del.setToolTip("Delete mod from Stash")
        btn_del.setProperty("iconBtn", "true")
        btn_del.setProperty("danger", "true")
        btn_del.clicked.connect(lambda _, m=mod: self.delete_mod(m))
        actions_layout.addWidget(btn_del)

        self.table_mods.setCellWidget(row, 6, actions_widget)

    self.update_bulk_actions_bar()

    if unknown_fika_mods:
        self.fika_sync_thread = FikaSyncThread(unknown_fika_mods, self)
        self.fika_sync_thread.updated.connect(self.on_fika_updated)
        self.fika_sync_thread.start()


def _on_mod_row_checked(self, mod, checked):
    if not hasattr(self, "selected_mod_keys"):
        self.selected_mod_keys = set()
    if checked:
        self.selected_mod_keys.add(mod["name"])
    else:
        self.selected_mod_keys.discard(mod["name"])
    self.update_bulk_actions_bar()


def update_bulk_actions_bar(self):
    selected_mods = self.get_selected_installed_mods()
    cnt = len(selected_mods)
    total_pkgs = len(getattr(self, "all_installed_mods", []))
    if hasattr(self, "lbl_bulk_count"):
        self.lbl_bulk_count.setText(f"{cnt} of {total_pkgs} selected")

    if hasattr(self, "btn_bulk_enable"):
        self.btn_bulk_enable.setEnabled(cnt > 0)
        self.btn_bulk_disable.setEnabled(cnt > 0)
        self.btn_bulk_delete.setEnabled(cnt > 0)


def get_selected_installed_mods(self):
    selected_keys = getattr(self, "selected_mod_keys", set())
    return [m for m in getattr(self, "all_installed_mods", []) if m["name"] in selected_keys]


def select_all_installed_mods(self):
    self.selected_mod_keys = set(m["name"] for m in getattr(self, "all_installed_mods", []))
    if hasattr(self, "row_checkboxes"):
        for chk, _ in self.row_checkboxes:
            chk.blockSignals(True)
            chk.setChecked(True)
            chk.blockSignals(False)
    self.update_bulk_actions_bar()


def deselect_all_installed_mods(self):
    self.selected_mod_keys = set()
    if hasattr(self, "row_checkboxes"):
        for chk, _ in self.row_checkboxes:
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)
    self.update_bulk_actions_bar()


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
                create_relative_symlink(item, live_link)
            for item, live_link, _ in server_items:
                create_relative_symlink(item, live_link)
            enabled_count += 1

    self.load_installed_mods()
    if hasattr(self, "toast"):
        self.toast.success(f" Enabled {enabled_count} mod package(s)!")
    else:
        QMessageBox.information(self, "Bulk Enable Complete", f" Enabled <b>{enabled_count}</b> mod package(s)!")


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
                remove_path(live_link)
            for _, live_link, _ in server_items:
                remove_path(live_link)
            disabled_count += 1

    self.load_installed_mods()
    if hasattr(self, "toast"):
        self.toast.info(f"⏸ Disabled {disabled_count} mod package(s)!")
    else:
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

        self.selected_mod_keys = set()
        self.load_installed_mods()
        if hasattr(self, "toast"):
            self.toast.error(f" Deleted {len(selected)} mod package(s)!")
        else:
            QMessageBox.information(self, "Bulk Delete Complete", f" Deleted <b>{len(selected)}</b> mod package(s)!")


def open_author_profile(self, mod):
    url = resolve_author_profile_url(mod)
    if url:
        QDesktopServices.openUrl(QUrl(url))


def open_mod_folder(self, mod):
    staged_p = mod.get("staged_path")
    if staged_p and staged_p.exists():
        folder_to_open = staged_p if staged_p.is_dir() else staged_p.parent
        try:
            host.popen(["xdg-open", folder_to_open])
        except Exception as e:
            QMessageBox.warning(self, "Open Folder Error", f"Could not open file manager: {e}")


def open_mod_web(self, mod):
    meta = load_mod_meta(mod["staged_path"]) if mod.get("staged_path") else {}
    matched = find_best_catalog_match_global(mod["name"])
    link = meta.get("link") or (matched.get("link") if matched else None)
    if not link:
        query = urllib.parse.quote(mod["name"])
        link = f"https://sp-mod.com/mods?query={query}"
    QDesktopServices.openUrl(QUrl(link))


def on_fika_updated(self, mod_name, fika_status):
    for row in range(self.table_mods.rowCount()):
        item_name = self.table_mods.item(row, 2)
        if item_name and item_name.text().lower() == mod_name.lower():
            fika_widget = self.table_mods.cellWidget(row, 5)
            if fika_widget:
                lbl = fika_widget.findChild(QLabel)
                if lbl:
                    if "Compatible" in fika_status or fika_status == "Yes":
                        lbl.setText("Compatible")
                        lbl.setProperty("pill", "success")
                    elif "Incompatible" in fika_status or fika_status == "No":
                        lbl.setText("Issues")
                        lbl.setProperty("pill", "warn")
                    else:
                        lbl.setText("Unknown")
                        lbl.setProperty("pill", "muted")
                    lbl.style().unpolish(lbl)
                    lbl.style().polish(lbl)


def _render_installed_detail_html(self, mod, matched, desc_html):
    meta = load_mod_meta(mod.get("staged_path")) or {}
    author = meta.get("author") or "Community"
    if matched:
        if not author or author == "Community":
            author = matched.get("creator") or author

    ver = meta.get("version") or "unknown"
    spt_ver = meta.get("spt_version") or (matched.get("spt_version") if matched else "")
    cat = matched.get("category", "Other") if matched else "Other"

    disabled = mod.get("disabled", False)
    status_text = "Disabled" if disabled else "Enabled"
    status_color = DANGER if disabled else SUCCESS

    mod_type = "Client/Server"
    if mod.get("has_client") and not mod.get("has_server"):
        mod_type = "Client"
    elif mod.get("has_server") and not mod.get("has_client"):
        mod_type = "Server"

    fika = meta.get("fika_status", "Unknown")
    if "Compatible" in fika:
        fika_color = SUCCESS
    elif "Incompatible" in fika:
        fika_color = DANGER
    else:
        fika_color = WARNING

    img_url = matched.get("image_url", "") if matched else ""
    web_url = resolve_author_profile_url({"name": mod["name"], "author": author}) if author != "Community" else ""
    mod_link = matched.get("link", "") if matched else ""

    image_html = (
        f"<div style=\"text-align:center; margin-bottom:14px;\">"
        f"<img src=\"{html.escape(img_url)}\" style=\"max-width:100%; max-height:180px; border-radius:8px; border:1px solid {BORDER};\" />"
        f"</div>"
        if img_url else ""
    )

    open_page_html = (
        f"<a href=\"{html.escape(mod_link)}\" style=\"display:inline-block; background-color:rgba(124,140,255,0.10); border:1px solid rgba(124,140,255,0.25); border-radius:6px; padding:6px 12px; color:{ACCENT}; text-decoration:none; font-weight:600; font-size:12px; margin-bottom:14px;\">Open Page</a>"
        if mod_link else ""
    )

    spt_row = f"<tr><td style=\"color:{TEXT_MUTED};\"><b>SPT Version:</b></td><td>{html.escape(spt_ver)}</td></tr>" if spt_ver else ""
    author_link = f"| <a href=\"{html.escape(web_url)}\" style=\"color:{ACCENT};\">Author profile</a>" if web_url else ""

    return f"""<div style=\"color:{TEXT}; font-size:13px; line-height:1.5;\">
        <h2 style=\"margin:0 0 6px 0; font-size:17px;\">{html.escape(mod['name'])} <span style=\"color:{ACCENT};\">v{html.escape(ver)}</span></h2>
        <p style=\"color:{TEXT_MUTED}; margin:0 0 10px 0;\">by <span style=\"color:{ACCENT};\">{html.escape(author)}</span> {author_link}</p>
        {open_page_html}
        {image_html}
        <div style=\"background-color:{BG}; border:1px solid {SURFACE_2}; border-radius:8px; padding:10px; margin:12px 0 12px 0;\">
            <table style=\"width:100%; font-size:12px; color:{TEXT}; border-collapse:collapse;\">
                <tr><td style=\"color:{TEXT_MUTED}; width:100px;\"><b>Status:</b></td><td><span style=\"color:{status_color}; font-weight:600;\">{status_text}</span></td></tr>
                <tr><td style=\"color:{TEXT_MUTED};\"><b>Type:</b></td><td>{html.escape(mod_type)}</td></tr>
                <tr><td style=\"color:{TEXT_MUTED};\"><b>Category:</b></td><td>{html.escape(cat)}</td></tr>
                {spt_row}
                <tr><td style=\"color:{TEXT_MUTED};\"><b>Fika:</b></td><td><span style=\"color:{fika_color}; font-weight:600;\">{html.escape(fika)}</span></td></tr>
            </table>
        </div>
        {desc_html}
    </div>"""


def _on_full_description_fetched(self, mod_name, full_desc):
    if not self._installed_detail_popup or not self._installed_detail_popup.isVisible():
        return
    current = getattr(self, "current_selected_installed_mod", None)
    if not current or current.get("name") != mod_name:
        return
    matched = find_best_catalog_match_global(mod_name)
    body = f"<p>{html.escape(full_desc)}</p>" if full_desc else ""
    self.installed_detail.setHtml(self._render_installed_detail_html(current, matched, body))


def show_installed_mod_detail(self, mod):
    matched = find_best_catalog_match_global(mod["name"])
    desc_html = matched.get("description", "") if matched else ""

    # Strip the cached catalog wrapper (image, title, author, hr) and leave only the body excerpt.
    desc_html = re.sub(r'<img[^>]*>', '', desc_html, flags=re.IGNORECASE)
    desc_html = re.sub(r"<div[^>]*margin-bottom:\s*12px[^>]*>[\\s\\S]*?</div>", '', desc_html, count=1, flags=re.IGNORECASE)
    desc_html = re.sub(r'<div[^>]*>\s*</div>', '', desc_html, flags=re.IGNORECASE)
    desc_html = re.split(r'<hr\s*/?>', desc_html, maxsplit=1, flags=re.IGNORECASE)[-1]
    desc_html = re.sub(r'<p[^>]*>\s*<a[^>]*href=[^>]*sp-mod\.com[^>]*>.*?</a>\s*</p>', '', desc_html, count=1, flags=re.IGNORECASE | re.DOTALL)
    desc_html = desc_html.strip()

    mod_link = matched.get("link", "") if matched else ""
    if desc_html.rstrip().endswith('...') and mod_link:
        desc_html += f"<p style=\"color:{TEXT_MUTED}; margin-top:10px;\">Full description available on <a href=\"{html.escape(mod_link)}\" style=\"color:{ACCENT};\">sp-mod.com</a>.</p>"

    body_html = f"<p>{html.escape(desc_html)}</p>" if desc_html else ""

    if not self._installed_detail_popup:
        self._installed_detail_popup = QFrame(self.tab_installed)
        self._installed_detail_popup.setObjectName("modDetailPopup")
        self._installed_detail_popup.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self._installed_detail_popup.setStyleSheet(f"""
            QFrame#modDetailPopup {{
                background-color: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
            QFrame#modDetailPopup QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        self._installed_detail_popup.setFixedSize(420, 520)
        popup_layout = QVBoxLayout(self._installed_detail_popup)
        popup_layout.setContentsMargins(12, 12, 12, 12)
        popup_layout.setSpacing(0)

        self.installed_detail = RemoteImageTextBrowser(self._installed_detail_popup)
        self.installed_detail.setOpenExternalLinks(True)
        self.installed_detail.setStyleSheet(f"background-color: transparent; border: none; color: {TEXT}; padding: 0px;")
        popup_layout.addWidget(self.installed_detail)

    self.installed_detail.setHtml(self._render_installed_detail_html(mod, matched, body_html))

    cursor_pos = QCursor.pos()
    self._installed_detail_popup.move(cursor_pos.x() + 16, cursor_pos.y() + 12)
    self._installed_detail_popup.show()
    self._installed_detail_popup.raise_()
    self._installed_detail_popup.activateWindow()

    self.current_selected_installed_mod = mod

    fetcher = ModDetailFetcherThread(mod["name"], parent=self)
    fetcher.fetched.connect(self._on_full_description_fetched)
    fetcher.start()



def show_installed_table_context_menu(self, pos):
    item = self.table_mods.itemAt(pos)
    if not item:
        return
    row = item.row()
    mod_item = self.table_mods.item(row, 2)
    if not mod_item:
        return
    mod = mod_item.data(Qt.UserRole)
    if not mod:
        return

    menu = QMenu(self)
    menu.setStyleSheet(f"""
        QMenu {{ background-color: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px; }}
        QMenu::item {{ padding: 8px 24px; border-radius: 4px; font-weight: 500; }}
        QMenu::item:selected {{ background-color: {SURFACE_2}; color: {ACCENT}; }}
        QMenu::separator {{ height: 1px; background-color: {BORDER}; margin: 4px 0px; }}
    """)

    act_open_folder = menu.addAction(" Open Folder in File Manager")
    act_open_web = menu.addAction(" Open Web Page on sp-mod.com")

    meta = load_mod_meta(mod["staged_path"]) or {}
    author_str = meta.get("author")
    if not author_str or author_str == "Community":
        matched = find_best_catalog_match_global(mod["name"])
        if matched:
            author_str = matched.get("creator")

    act_author_search = None
    if author_str and author_str != "Community":
        act_author_search = menu.addAction(f" Open {author_str}'s Profile on sp-mod.com")

    menu.addSeparator()

    is_disabled = mod.get("disabled", False)
    act_toggle = menu.addAction(" Enable Mod" if is_disabled else " Disable Mod")
    act_check_upd = menu.addAction(" Check for Updates")
    menu.addSeparator()

    act_copy_path = menu.addAction(" Copy Path to Clipboard")
    menu.addSeparator()

    act_delete = menu.addAction(" Delete Mod Package")

    global_pos = self.table_mods.viewport().mapToGlobal(pos)
    action = menu.exec(global_pos)
    if not action:
        return

    if action == act_open_folder:
        self.open_mod_folder(mod)
    elif action == act_open_web:
        self.open_mod_web(mod)
    elif act_author_search and action == act_author_search:
        self.open_author_profile(mod)
    elif action == act_toggle:
        self.toggle_mod(mod)
    elif action == act_check_upd:
        self.check_installed_mod_updates()
    elif action == act_copy_path:
        staged_p = mod.get("staged_path")
        if staged_p:
            QApplication.clipboard().setText(str(staged_p))
            if hasattr(self, "toast"):
                self.toast.info(" Path copied to clipboard")
            else:
                QMessageBox.information(self, "Copied Path", f" Path copied to clipboard:\n\n{staged_p}")
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

        curr_ver = (meta.get("version") if meta else "") or "0"  # unknown version → offer the update
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
        if hasattr(self, "toast"):
            self.toast.success(" All installed mods are up to date!")
        else:
            QMessageBox.information(
                self,
                "Up to Date!",
                " <b>All installed mods are up to date!</b><br>No newer versions were found on sp-mod.com.",
            )
        return

    upd_list = "\n".join(
        f"• <b>{html.escape(u['title'])}</b>: v{u['current_ver']} → <b style='color:{SUCCESS};'>v{u['latest_ver']}</b>"
        for u in updates[:15]
    )
    extra = f"\n...and {len(updates) - 15} more" if len(updates) > 15 else ""

    reply = QMessageBox.question(
        self,
        "Mod Updates Available",
        f" <b>{len(updates)} mod update(s) available</b>:\n\n"
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


def filter_installed_mods(self, text=None):
    query = (text if text is not None else self.installed_search.text()).lower().strip()
    mode = getattr(self, "current_filter_mode", "all")

    filtered = []
    for m in getattr(self, "all_installed_mods", []):
        if query and query not in m["name"].lower() and query not in m["type"].lower():
            continue

        if mode == "enabled" and m.get("disabled", False):
            continue
        elif mode == "client" and not m.get("has_client", False):
            continue
        elif mode == "server" and not m.get("has_server", False):
            continue
        elif mode == "fika":
            meta = load_mod_meta(m.get("staged_path")) if m.get("staged_path") else {}
            f_stat = meta.get("fika_status", "")
            if not ("Compatible" in f_stat or f_stat == "Yes" or "fika" in m["name"].lower()):
                continue

        filtered.append(m)

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
                            link_p = (paths.SERVER_MODS_DIR if is_srv else paths.CLIENT_MODS_DIR) / dep_p.name
                            remove_path(link_p)
                            create_relative_symlink(dep_p, link_p)

            client_items = mod.get("client_items", [])
            server_items = mod.get("server_items", [])

            for item, live_link, _ in client_items:
                create_relative_symlink(item, live_link)

            for item, live_link, _ in server_items:
                create_relative_symlink(item, live_link)

            if hasattr(self, "toast"):
                self.toast.success(f" Enabled {mod['name']}")
        else:
            client_items = mod.get("client_items", [])
            server_items = mod.get("server_items", [])

            for _, live_link, _ in client_items:
                remove_path(live_link)

            for _, live_link, _ in server_items:
                remove_path(live_link)

            if hasattr(self, "toast"):
                self.toast.info(f"Disabled {mod['name']}")

        self.load_installed_mods()
    except Exception as e:
        QMessageBox.critical(self, "Error", f"Failed to toggle mod: {e}")


def audit_installed_dependencies(self):
    if not hasattr(self, "all_installed_mods") or not self.all_installed_mods:
        if hasattr(self, "toast"):
            self.toast.info("No installed mods found to audit.")
        else:
            QMessageBox.information(self, "Audit Dependencies", "No installed mods found to audit.")
        return

    progress = QProgressDialog(
        " Auditing dependencies for installed mods...", "Cancel", 0, len(self.all_installed_mods), self
    )
    progress.setWindowModality(Qt.WindowModal)
    progress.show()

    issues = []

    for i, mod in enumerate(self.all_installed_mods):
        if progress.wasCanceled():
            break
        progress.setValue(i)
        progress.setLabelText(f" Auditing ({i + 1}/{len(self.all_installed_mods)}): {mod['name']}...")
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
        if hasattr(self, "toast"):
            self.toast.success(" All dependencies satisfied!")
        else:
            QMessageBox.information(
                self, "Audit Complete", " All installed mods have their required dependencies installed and enabled!"
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
            msg += f"  - <span style='color:{WARNING};'>Disabled in Stash:</span> {d['title']}<br/>"
            all_disabled_to_enable.append(d)
        for m in item["missing"]:
            msg += f"  - <span style='color:{DANGER};'>Missing:</span> {m['title']}<br/>"
            all_missing_to_download.append(m)
        msg += "<br/>"

    msg += "Would you like to automatically enable disabled Stash dependencies and download missing dependencies?"

    reply = QMessageBox.question(self, "Dependency Audit Results", msg, QMessageBox.Yes | QMessageBox.No)

    if reply == QMessageBox.Yes:
        for d in all_disabled_to_enable:
            dep_p = d["path"]
            is_srv = "server" in str(dep_p).lower()
            link_p = (paths.SERVER_MODS_DIR if is_srv else paths.CLIENT_MODS_DIR) / dep_p.name
            create_relative_symlink(dep_p, link_p)

        if all_missing_to_download:
            self.start_dependency_queue_download(all_missing_to_download, None)

        self.load_installed_mods()
        if hasattr(self, "toast"):
            self.toast.success(" Dependency auto-fix process completed!")
        else:
            QMessageBox.information(self, "Audit Auto-Fix", " Dependency auto-fix process completed!")


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
            self.selected_mod_keys.discard(mod["name"])
            self.load_installed_mods()
            if hasattr(self, "toast"):
                self.toast.error(f" Deleted '{mod['name']}'")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete mod: {e}")
