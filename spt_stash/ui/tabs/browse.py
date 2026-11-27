#!/usr/bin/env python3
"""SPT Stash — Browse sp-mod.com Forge Catalog tab."""

import html

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ... import paths
from ...catalog.dependencies import check_dep_status, fetch_mod_dependencies_sync
from ...catalog.workers import DependencyFetcherThread, RSSFetcherThread
from ...staging.links import create_relative_symlink
from ...staging.workers import ModDownloaderThread, ModInstallerThread
from ...system.hardware import detect_installed_spt_version
from ..dialogs import StageInstallDialog
from ..theme import ACCENT, BG, BORDER, DANGER, SUCCESS, SURFACE, TEXT, TEXT_MUTED, WARNING
from ..widgets import ModItemDelegate, RemoteImageTextBrowser, SearchField, _nav_pixmap


def setup_browse_tab(self):
    layout = QVBoxLayout(self.tab_browse)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(12)

    filter_layout = QHBoxLayout()
    filter_layout.setSpacing(8)

    self.browse_search = SearchField(width=260, placeholder="Search online mods...")
    self.browse_search.textChanged.connect(self.filter_remote_mods)
    filter_layout.addWidget(self.browse_search)

    self.combo_category = QComboBox()
    self.combo_category.addItem("All Categories")
    self.combo_category.currentTextChanged.connect(self.filter_remote_mods)
    filter_layout.addWidget(self.combo_category)

    self.combo_sort = QComboBox()
    self.combo_sort.addItems(
        [
            "Sort: Newest",
            "Sort: Recently Updated",
            "Sort: Most Downloaded",
            "Sort: Most Favourited",
            "Sort: Most Endorsed",
        ]
    )
    self.combo_sort.currentTextChanged.connect(self.filter_remote_mods)
    filter_layout.addWidget(self.combo_sort)

    self.installed_spt_ver = detect_installed_spt_version()
    self.chk_installed_version = QCheckBox(f"Filter for Installed ({self.installed_spt_ver})")
    self.chk_installed_version.setStyleSheet(f"font-weight: 600; color: {TEXT_MUTED};")
    self.chk_installed_version.setChecked(True)
    self.chk_installed_version.toggled.connect(self.filter_remote_mods)
    filter_layout.addWidget(self.chk_installed_version)

    btn_fetch = QPushButton("Refresh")
    btn_fetch.setIcon(QIcon(_nav_pixmap("refresh", size=14, color=TEXT_MUTED)))
    btn_fetch.setIconSize(QSize(14, 14))
    btn_fetch.setProperty("role", "ghost")
    btn_fetch.setProperty("size", "sm")
    btn_fetch.setToolTip("Refresh catalog feed")
    btn_fetch.clicked.connect(lambda: self.fetch_remote_mods(force_refresh=True))
    filter_layout.addWidget(btn_fetch)

    layout.addLayout(filter_layout)

    splitter = QSplitter(Qt.Horizontal)
    splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {BORDER}; width: 1px; }}")

    self.list_remote = QListWidget()
    self.list_remote.setSpacing(4)
    self.list_remote.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self.list_remote.setItemDelegate(ModItemDelegate(self.list_remote))
    self.list_remote.itemSelectionChanged.connect(self.on_remote_mod_selected)
    splitter.addWidget(self.list_remote)

    right_widget = QWidget()
    right_layout = QVBoxLayout(right_widget)
    right_layout.setContentsMargins(12, 0, 0, 0)
    right_layout.setSpacing(10)

    # Selected mod action card (always visible at top)
    self.detail_action_card = QFrame()
    self.detail_action_card.setStyleSheet(f"""
        QFrame {{
            background-color: {SURFACE};
            border: 1px solid {BORDER};
            border-radius: 10px;
            padding: 12px 14px;
        }}
        QFrame QLabel {{
            background: transparent;
            border: none;
        }}
    """)
    action_layout = QHBoxLayout(self.detail_action_card)
    action_layout.setContentsMargins(10, 6, 10, 6)
    action_layout.setSpacing(10)

    self.lbl_detail_title = QLabel("No mod selected")
    self.lbl_detail_title.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: 600;")
    action_layout.addWidget(self.lbl_detail_title)
    action_layout.addStretch()

    self.lbl_detail_size = QLabel("")
    self.lbl_detail_size.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
    action_layout.addWidget(self.lbl_detail_size)

    self.btn_download_mod = QPushButton("Install")
    self.btn_download_mod.setIcon(QIcon(_nav_pixmap("install", size=14, color=BG)))
    self.btn_download_mod.setIconSize(QSize(14, 14))
    self.btn_download_mod.setProperty("role", "success")
    self.btn_download_mod.setProperty("size", "sm")
    self.btn_download_mod.clicked.connect(self.start_mod_download)
    self.btn_download_mod.setEnabled(False)
    action_layout.addWidget(self.btn_download_mod)

    self.btn_open_web = QPushButton("Open Page")
    self.btn_open_web.setIcon(QIcon(_nav_pixmap("external", size=14, color=TEXT_MUTED)))
    self.btn_open_web.setIconSize(QSize(14, 14))
    self.btn_open_web.setProperty("role", "ghost")
    self.btn_open_web.setProperty("size", "sm")
    self.btn_open_web.clicked.connect(self.open_mod_in_browser)
    self.btn_open_web.setEnabled(False)
    action_layout.addWidget(self.btn_open_web)

    self.detail_action_card.setVisible(False)
    right_layout.addWidget(self.detail_action_card)

    self.web_detail = RemoteImageTextBrowser()
    self.web_detail.setOpenExternalLinks(True)
    self.web_detail.setStyleSheet(
        f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; color: {TEXT}; padding: 12px;"
    )
    right_layout.addWidget(self.web_detail)

    splitter.addWidget(right_widget)
    splitter.setSizes([430, 570])

    layout.addWidget(splitter)

    self.fetch_remote_mods(force_refresh=False)


def fetch_remote_mods(self, force_refresh=False):
    self.list_remote.clear()
    self.web_detail.setHtml(f"<h3 style='color:{TEXT_MUTED}; text-align:center; margin-top:40px;'>Loading catalog...</h3>")

    self.rss_thread = RSSFetcherThread(self)
    self.rss_thread.force_refresh = force_refresh
    self.rss_thread.progress.connect(
        lambda p: self.web_detail.setHtml(f"<h3 style='color:{TEXT_MUTED}; text-align:center; margin-top:40px;'>{p}</h3>")
    )
    self.rss_thread.fetched.connect(self.on_remote_mods_fetched)
    self.rss_thread.error.connect(
        lambda err: self.web_detail.setHtml(
            f"<h3 style='color:{DANGER}; text-align:center; margin-top:40px;'>Error fetching catalog: {err}</h3>"
        )
    )
    self.rss_thread.start()


def on_remote_mods_fetched(self, items):
    self.remote_mods = items

    site_categories = [
        "Equipment",
        "Hideout",
        "Items",
        "Locales",
        "Locations",
        "Models",
        "Other",
        "Overhauls",
        "Quests",
        "Retextures",
        "Tools",
        "Traders",
        "Weapons",
    ]
    present_categories = set(m.get("category", "Other") for m in items)

    self.combo_category.blockSignals(True)
    self.combo_category.clear()
    self.combo_category.addItem("All Categories")
    for c in site_categories:
        if c in present_categories:
            self.combo_category.addItem(c)
    for c in sorted(list(present_categories)):
        if c not in site_categories and c != "All Categories":
            self.combo_category.addItem(c)
    self.combo_category.blockSignals(False)

    self.filter_remote_mods()


def filter_remote_mods(self):
    query = self.browse_search.text().lower().strip()
    cat = self.combo_category.currentText()
    sort_mode = self.combo_sort.currentText() if hasattr(self, "combo_sort") else "Sort: Newest"
    only_compatible = self.chk_installed_version.isChecked() if hasattr(self, "chk_installed_version") else False
    installed_ver = getattr(self, "installed_spt_ver", "SPT 4.1.3")

    filtered = []
    for mod in self.remote_mods:
        mod_spt = mod.get("spt_version", "")
        if only_compatible and mod_spt and mod_spt != installed_ver:
            continue
        if cat != "All Categories" and mod["category"] != cat:
            continue
        if query and query not in mod["title"].lower() and query not in mod["creator"].lower():
            continue
        filtered.append(mod)

    # Apply sorting
    if sort_mode == "Sort: Most Downloaded":
        filtered.sort(key=lambda x: x.get("downloads", 0), reverse=True)
    elif sort_mode == "Sort: Most Endorsed" or sort_mode == "Sort: Most Favourited":
        filtered.sort(key=lambda x: x.get("endorsements", 0), reverse=True)

    self.list_remote.clear()
    for mod in filtered:
        item = QListWidgetItem()
        item.setData(Qt.UserRole, mod)
        self.list_remote.addItem(item)

    # Reset detail pane to empty state when filter changes selection.
    self.list_remote.clearSelection()
    self.web_detail.setHtml(f"""
        <div style='color:{TEXT_MUTED}; text-align:center; padding:48px 24px; font-size:14px;'>
            <div style='font-size:28px; margin-bottom:12px;'></div>
            <div style='color:{TEXT}; font-weight:600; margin-bottom:8px;'>No mod selected</div>
            <div>Select a mod from the list to view details, dependencies, and install options.</div>
        </div>
    """)


def render_mod_detail_html(self, mod):
    creator = html.escape(mod.get("creator", "Community"))
    ver = html.escape(str(mod.get("version", "")))
    spt_ver = html.escape(mod.get("spt_version", ""))
    cat = html.escape(mod.get("category", "Other"))
    dl_cnt = mod.get("downloads", 0)
    end_cnt = mod.get("endorsements", 0)

    guid = mod.get("guid", "")
    license_str = mod.get("license", "")
    src_code = mod.get("source_code", "")
    vt_url = mod.get("virustotal", "")
    fika_status = mod.get("fika_status", "Unknown")
    has_ai = mod.get("has_ai", False)


    guid_html = (
        f"<tr><td style='color:{TEXT_MUTED}; padding:4px 0; width:130px;'><b>GUID:</b></td><td><code style='color:{SUCCESS}; font-family:monospace;'>{html.escape(guid)}</code></td></tr>"
        if guid
        else ""
    )
    license_html = (
        f"<tr><td style='color:{TEXT_MUTED}; padding:4px 0;'><b>License:</b></td><td>{html.escape(license_str)}</td></tr>"
        if license_str
        else ""
    )
    src_html = (
        f"<tr><td style='color:{TEXT_MUTED}; padding:4px 0;'><b>Source Code:</b></td><td><a href='{html.escape(src_code)}' style='color:{ACCENT};'>{html.escape(src_code)}</a></td></tr>"
        if src_code
        else ""
    )
    vt_html = (
        f"<tr><td style='color:{TEXT_MUTED}; padding:4px 0;'><b>VirusTotal:</b></td><td><a href='{html.escape(vt_url)}' style='color:{SUCCESS};'>Clean Scan Results</a></td></tr>"
        if vt_url
        else ""
    )
    ai_html = (
        f"<tr><td style='color:{TEXT_MUTED}; padding:4px 0;'><b>AI Content:</b></td><td><span style='color:{ACCENT};'>Includes AI Content</span></td></tr>"
        if has_ai
        else ""
    )

    if "Compatible" in fika_status or fika_status == "Yes":
        fika_badge = f"<span style='color:{SUCCESS}; font-weight:bold;'>Fika Compatible Version Available</span>"
    elif "Incompatible" in fika_status or fika_status == "No":
        fika_badge = f"<span style='color:{DANGER}; font-weight:bold;'>Fika Incompatible</span>"
    else:
        fika_badge = f"<span style='color:{WARNING};'>Compatibility Unknown</span>"

    stats_html = f" {dl_cnt:,} downloads  •   {end_cnt:,} endorsements" if (dl_cnt or end_cnt) else ""

    card_html = f"""
    <div style='background-color:{SURFACE}; border:1px solid {BORDER}; border-radius:8px; padding:14px; margin-bottom:14px;'>
        <h3 style='color:{TEXT}; margin:0 0 12px 0; font-size:14px;'>Mod Details & Author Info</h3>
        <table style='width:100%; font-size:12.5px; color:{TEXT}; border-collapse:collapse;'>
            <tr><td style='color:{TEXT_MUTED}; padding:4px 0; width:130px;'><b>Author:</b></td><td><b style='color:{ACCENT};'>{creator}</b></td></tr>
            <tr><td style='color:{TEXT_MUTED}; padding:4px 0;'><b>Version:</b></td><td><span style='color:{TEXT}; font-weight:bold;'>v{ver}</span></td></tr>
            <tr><td style='color:{TEXT_MUTED}; padding:4px 0;'><b>Target SPT:</b></td><td><span style='color:{SUCCESS}; font-weight:bold;'>{spt_ver}</span></td></tr>
            <tr><td style='color:{TEXT_MUTED}; padding:4px 0;'><b>Category:</b></td><td><span style='background-color:rgba(124,140,255,0.12); color:{ACCENT}; padding:2px 8px; border-radius:4px;'>{cat}</span></td></tr>
            {guid_html}
            {license_html}
            {src_html}
            {vt_html}
            <tr><td style='color:{TEXT_MUTED}; padding:4px 0;'><b>Fika Status:</b></td><td>{fika_badge}</td></tr>
            {ai_html}
            {"<tr><td style='color:" + TEXT_MUTED + "; padding:4px 0;'><b>Stats:</b></td><td>" + stats_html + "</td></tr>" if stats_html else ""}
        </table>
    </div>
    """
    deps = mod.get("dependencies", [])
    dep_html = ""
    if deps:
        dep_html = f"<div style='background-color:{SURFACE}; border:1px solid {BORDER}; border-radius:8px; padding:12px; margin-top:14px;'>"
        dep_html += f"<h3 style='color:{TEXT}; margin:0 0 8px 0; font-size:14px;'>Required Dependencies ({len(deps)}):</h3>"
        for d in deps:
            st = d.get("status")
            if st == "ENABLED" or d.get("installed"):
                status_text = f"<span style='color:{SUCCESS}; font-weight:bold;'>(Installed & Enabled)</span>"
            elif st == "STAGED_DISABLED":
                status_text = f"<span style='color:{WARNING}; font-weight:bold;'>(In Stash, Disabled — Auto-enables on Download)</span>"
            else:
                status_text = f"<span style='color:{DANGER}; font-weight:bold;'>(Missing — Auto-installs on Download)</span>"

            dep_html += f"<p style='margin:4px 0; color:{TEXT};'>• <b>{d['title']}</b> {status_text}</p>"
        dep_html += "</div>"

    return mod.get("description", "") + dep_html + card_html


def on_remote_mod_selected(self):
    items = self.list_remote.selectedItems()
    if not items:
        self.btn_open_web.setEnabled(False)
        self.btn_download_mod.setEnabled(False)
        self.detail_action_card.setVisible(False)
        self.lbl_detail_title.setText("No mod selected")
        self.lbl_detail_size.setText("")
        self.web_detail.setHtml(f"""
        <div style='color:{TEXT_MUTED}; text-align:center; padding:48px 24px; font-size:14px;'>
            <div style='color:{TEXT}; font-weight:600; margin-bottom:8px;'>No mod selected</div>
            <div>Select a mod from the list to view details, dependencies, and install options.</div>
        </div>
        """)
        return

    mod = items[0].data(Qt.UserRole)
    self.current_selected_remote_mod = mod
    self.btn_open_web.setEnabled(True)
    self.btn_download_mod.setEnabled(True)
    self.detail_action_card.setVisible(True)
    self.lbl_detail_title.setText(mod.get("title", "Mod"))

    status, _ = check_dep_status(mod.get("title", ""))
    if status == "ENABLED":
        self.btn_download_mod.setText("Disable")
        self.btn_download_mod.setProperty("role", "danger")
    elif status == "STAGED_DISABLED":
        self.btn_download_mod.setText("Enable")
        self.btn_download_mod.setProperty("role", "success")
    else:
        self.btn_download_mod.setText("Install")
        self.btn_download_mod.setProperty("role", "success")
    # Force stylesheet re-apply
    self.btn_download_mod.setStyleSheet(self.btn_download_mod.styleSheet())

    self.web_detail.setHtml(self.render_mod_detail_html(mod))

    # Fetch dependencies in background thread
    self.dep_thread = DependencyFetcherThread(mod, self)
    self.dep_thread.fetched.connect(self.on_dependencies_fetched)
    self.dep_thread.start()


def on_dependencies_fetched(self, mod_info, deps):
    if not hasattr(self, "current_selected_remote_mod") or self.current_selected_remote_mod.get("link") != mod_info.get(
        "link"
    ):
        return

    mod_info["dependencies"] = deps
    self.web_detail.setHtml(self.render_mod_detail_html(mod_info))


def start_mod_download(self):
    if not hasattr(self, "current_selected_remote_mod") or not self.current_selected_remote_mod:
        return

    mod = self.current_selected_remote_mod

    # Instant toggle for already installed/staged mods
    mod_status, target_path = check_dep_status(mod.get("title", ""))

    if mod_status == "ENABLED":
        # Only ever unlink; a real (non-symlink) folder is the user's data and is never deleted from here.
        if target_path and target_path.is_symlink():
            target_path.unlink()
        elif target_path:
            QMessageBox.warning(
                self,
                "Cannot Disable",
                f"<b>{mod['title']}</b> is installed manually at <code>{target_path}</code>.<br>"
                "Open the Installed tab to manage it.",
            )
            return
        self.load_installed_mods()
        self.list_remote.viewport().update()
        self.on_remote_mod_selected()
        QMessageBox.information(self, "Mod Disabled", f"⏸ <b>{mod['title']}</b> is now disabled.")
        return

    if mod_status == "STAGED_DISABLED":
        if target_path:
            is_server = "server" in str(target_path).lower()
            live_dir = paths.SERVER_MODS_DIR if is_server else paths.CLIENT_MODS_DIR
            live_link = live_dir / target_path.name
            create_relative_symlink(target_path, live_link)
        self.load_installed_mods()
        self.list_remote.viewport().update()
        self.on_remote_mod_selected()
        QMessageBox.information(self, "Mod Enabled", f" <b>{mod['title']}</b> is now enabled in your game!")
        return

    if "dependencies" not in mod or mod["dependencies"] is None or not mod["dependencies"]:
        self.btn_download_mod.setEnabled(False)
        self.btn_download_mod.setText("Checking dependencies...")
        QApplication.processEvents()
        mod["dependencies"] = fetch_mod_dependencies_sync(mod)

    deps = mod.get("dependencies", [])
    staged_disabled_deps = [d for d in deps if d.get("status") == "STAGED_DISABLED"]

    if staged_disabled_deps:
        names = "\n".join(f"• {d['title']}" for d in staged_disabled_deps)
        reply = QMessageBox.question(
            self,
            "Enable Required Dependencies?",
            f"<b>{mod['title']}</b> requires the following dependency mod(s) which are currently disabled in your Stash:\n\n"
            f"{names}\n\n"
            f"Would you like to enable these dependencies as well?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        )
        if reply == QMessageBox.Cancel:
            self.btn_download_mod.setEnabled(True)
            self.btn_download_mod.setText("Install")
            return
        if reply == QMessageBox.Yes:
            for dep in staged_disabled_deps:
                staged_path = dep["path"]
                is_server = "server" in str(staged_path).lower()
                live_dir = paths.SERVER_MODS_DIR if is_server else paths.CLIENT_MODS_DIR
                live_link = live_dir / staged_path.name
                create_relative_symlink(staged_path, live_link)
                dep["status"] = "ENABLED"
                dep["installed"] = True
            self.load_installed_mods()

    missing_deps = [
        d for d in deps if d.get("status") == "MISSING" or (not d.get("installed") and d.get("status") != "ENABLED")
    ]

    if missing_deps:
        dep_names = "\n".join(f"• {d['title']}" for d in missing_deps)
        reply = QMessageBox.question(
            self,
            "Auto-Install Missing Dependencies?",
            f"<b>{mod['title']}</b> requires <b>{len(missing_deps)} missing dependency mod(s)</b>:\n\n"
            f"{dep_names}\n\n"
            f"Would you like to automatically download and install these dependencies first?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        )
        if reply == QMessageBox.Cancel:
            self.btn_download_mod.setEnabled(True)
            self.btn_download_mod.setText("Install")
            return
        if reply == QMessageBox.Yes:
            self.start_dependency_queue_download(missing_deps, mod)
            return

    self.execute_single_mod_download(mod)


def execute_single_mod_download(self, mod):
    if mod.get("link"):
        mod["dependencies"] = fetch_mod_dependencies_sync(mod)

    dl_url = mod.get("download_url") or mod.get("link")
    self.btn_download_mod.setEnabled(False)
    self.btn_download_mod.setText("Downloading...")

    self.downloader_thread = ModDownloaderThread(dl_url, mod["title"])
    self.downloader_thread.progress.connect(
        lambda p, txt: self.show_download_progress(f"{mod['title']}: {txt}", p)
    )
    self.downloader_thread.finished.connect(lambda ok, msg, path: self.on_mod_downloaded(ok, msg, path, mod))
    self.downloader_thread.start()


def start_dependency_queue_download(self, missing_deps, target_mod):
    self.dep_queue = []
    for dep in missing_deps:
        matched = next(
            (
                m
                for m in self.remote_mods
                if m.get("link") == dep.get("link") or m["title"].lower() == dep["title"].lower()
            ),
            None,
        )
        if matched:
            self.dep_queue.append(matched)
        else:
            self.dep_queue.append(
                {
                    "title": dep["title"],
                    "link": dep["link"],
                    "download_url": dep["link"].replace("/mod/", "/mod/download/"),
                    "version": "latest",
                    "spt_version": getattr(self, "installed_spt_ver", "SPT 4.1.3"),
                }
            )

    self.dep_total = len(self.dep_queue)
    self.target_mod_after_deps = target_mod
    self.process_next_dependency_in_queue()


def process_next_dependency_in_queue(self):
    if not hasattr(self, "dep_queue") or not self.dep_queue:
        if hasattr(self, "target_mod_after_deps") and self.target_mod_after_deps:
            target = self.target_mod_after_deps
            self.target_mod_after_deps = None
            self.execute_single_mod_download(target)
        else:
            self.btn_download_mod.setEnabled(True)
            self.btn_download_mod.setText("Install")
            self.hide_download_progress()
            self.load_installed_mods()
            self.toast.success("All downloads installed")
        return

    dep_mod = self.dep_queue.pop(0)
    dl_url = dep_mod.get("download_url") or dep_mod.get("link")

    self.btn_download_mod.setEnabled(False)
    self.btn_download_mod.setText(f"Downloading dependency: {dep_mod['title']}...")

    self.dep_downloader = ModDownloaderThread(dl_url, dep_mod["title"])
    position = f"({self.dep_total - len(self.dep_queue)}/{self.dep_total}) "
    self.dep_downloader.progress.connect(
        lambda p, txt: self.show_download_progress(f"{position}{dep_mod['title']}: {txt}", p)
    )
    self.dep_downloader.finished.connect(lambda ok, msg, path: self.on_dependency_downloaded(ok, msg, path, dep_mod))
    self.dep_downloader.start()


def on_dependency_downloaded(self, success, message, archive_path, dep_mod):
    self.hide_download_progress()
    if not success:
        QMessageBox.critical(
            self, "Dependency Download Error", f"Failed to download dependency '{dep_mod['title']}': {message}"
        )
        self.btn_download_mod.setEnabled(True)
        self.btn_download_mod.setText("Install")
        return

    # Queued installs (dependencies, presets, updates) were already confirmed up front; no per-mod dialog.
    self.btn_download_mod.setText(f"Installing: {dep_mod['title']}...")
    self.show_download_progress(f"({self.dep_total - len(self.dep_queue)}/{self.dep_total}) Installing {dep_mod['title']}...")
    self.dep_installer = ModInstallerThread(archive_path, mod_info=dep_mod)
    self.dep_installer.finished.connect(lambda ok, msg: self.on_dependency_installed(ok, msg, archive_path))
    self.dep_installer.start()


def on_dependency_installed(self, success, message, archive_path):
    if archive_path and archive_path.exists():
        try:
            archive_path.unlink()
        except Exception:
            pass

    if not success:
        self.hide_download_progress()
        QMessageBox.critical(self, "Dependency Installation Error", f"Failed to install dependency: {message}")
        self.btn_download_mod.setEnabled(True)
        self.btn_download_mod.setText("Install")
        return

    self.load_installed_mods()
    QTimer.singleShot(1500, self.process_next_dependency_in_queue)  # space out requests to avoid 429s


def on_mod_downloaded(self, success, message, archive_path, mod_info):
    self.hide_download_progress()
    self.btn_download_mod.setEnabled(True)
    self.btn_download_mod.setText("Install")

    if not success:
        QMessageBox.critical(self, "Download Error", f"Failed to download mod: {message}")
        return

    stage_dialog = StageInstallDialog(archive_path, mod_info, parent=self)
    if stage_dialog.exec() == QDialog.Accepted:
        self.btn_download_mod.setEnabled(False)
        self.btn_download_mod.setText(f"Installing {mod_info['title']}...")
        self.show_download_progress(f"Installing {mod_info['title']}...")
        self.installer_thread = ModInstallerThread(archive_path, mod_info=mod_info)
        self.installer_thread.finished.connect(self.on_remote_mod_installed)
        self.installer_thread.start()
    else:
        if archive_path and archive_path.exists():
            try:
                archive_path.unlink()
            except Exception:
                pass


def on_remote_mod_installed(self, success, message):
    self.hide_download_progress()
    self.btn_download_mod.setEnabled(True)
    if not success:
        QMessageBox.critical(self, "Installation Error", f"Failed to install mod: {message}")
        return

    if hasattr(self, "load_installed_mods"):
        self.load_installed_mods()
    self.list_remote.viewport().update()
    self.on_remote_mod_selected()
    if hasattr(self, "toast"):
        self.toast.success(f"Installed {self.current_selected_remote_mod.get('title', 'mod')} successfully!")
    else:
        QMessageBox.information(self, "Installation Complete", f"Mod installed successfully: {message}")


def open_mod_in_browser(self):
    if hasattr(self, "current_selected_remote_mod") and self.current_selected_remote_mod.get("link"):
        QDesktopServices.openUrl(self.current_selected_remote_mod["link"])


# ------------------ Installer Tab ------------------
