#!/usr/bin/env python3
"""SPT Stash — main application window with V4 modern sidebar navigation."""

import json
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import load_config
from ..paths import apply_spt_root, ensure_dirs, find_app_icon, find_spt_root
from ..system.hardware import detect_installed_spt_version
from ..system.process import is_server_running, stop_server
from .dialogs import SettingsDialog
from .styles import get_app_stylesheet
from .tabs import browse as browse_tab
from .tabs import installed as installed_tab
from .tabs import installer as installer_tab
from .tabs import performance as performance_tab
from .tabs import presets as presets_tab
from .theme import DANGER, SUCCESS
from .toast import ToastManager


class SPTModManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SPT Stash — Mod Manager for Single-Player Tarkov")
        self.resize(1180, 760)

        # Set Global Theme Stylesheet
        self.setStyleSheet(get_app_stylesheet())

        # Toast notification engine
        self.toast = ToastManager(self)

        icon_path = find_app_icon()
        if icon_path and icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.remote_mods = []

        self.init_ui()
        self.check_server_status()

        # Timer for server status check
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.check_server_status)
        self.status_timer.start(3000)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        root_layout = QHBoxLayout(main_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(8, 16, 8, 8)
        sidebar_layout.setSpacing(4)

        # Brand row
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(6, 0, 6, 14)
        brand_row.setSpacing(10)
        icon_path = find_app_icon()
        if icon_path and icon_path.exists():
            lbl_icon = QLabel()
            pix = QPixmap(str(icon_path)).scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl_icon.setPixmap(pix)
            brand_row.addWidget(lbl_icon)
        lbl_name = QLabel("SPT Stash")
        lbl_name.setObjectName("brandName")
        brand_row.addWidget(lbl_name)
        brand_row.addStretch()
        sidebar_layout.addLayout(brand_row)

        # Navigation list (replaces QTabWidget)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        nav_items = [
            ("📦  Installed", "tab_installed"),
            ("🏷️  Presets", "tab_presets"),
            ("🔍  Browse Forge", "tab_browse"),
            ("⬇️  Install", "tab_installer"),
            ("⚡  Performance", "tab_performance"),
        ]
        self.nav_buttons = []
        for idx, (label, _attr) in enumerate(nav_items):
            btn = QPushButton(label)
            btn.setProperty("nav", "true")
            btn.setCheckable(True)
            if idx == 0:
                btn.setChecked(True)
            self.nav_group.addButton(btn)
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sidebar_layout.addStretch()

        # Server Control Panel at bottom of sidebar
        server_panel = QFrame()
        server_panel.setObjectName("serverPanel")
        server_layout = QVBoxLayout(server_panel)
        server_layout.setContentsMargins(8, 10, 8, 8)
        server_layout.setSpacing(8)

        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self.server_dot = QLabel("●")
        self.server_dot.setStyleSheet(f"color: {DANGER}; font-size: 13px;")
        status_row.addWidget(self.server_dot)
        self.server_status_lbl = QLabel("Server: Stopped")
        self.server_status_lbl.setObjectName("serverStatus")
        status_row.addWidget(self.server_status_lbl)
        status_row.addStretch()
        server_layout.addLayout(status_row)

        self.btn_launch = QPushButton("▶ Launch SPT")
        self.btn_launch.setProperty("role", "primary")
        self.btn_launch.setProperty("size", "lg")
        self.btn_launch.clicked.connect(self.launch_spt)
        server_layout.addWidget(self.btn_launch)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.btn_server_control = QPushButton("Start")
        self.btn_server_control.setProperty("role", "success")
        self.btn_server_control.setProperty("size", "sm")
        self.btn_server_control.clicked.connect(self.toggle_server_control)
        btn_row.addWidget(self.btn_server_control, 1)

        btn_settings = QPushButton("⚙ Settings")
        btn_settings.setProperty("role", "ghost")
        btn_settings.setProperty("size", "sm")
        btn_settings.clicked.connect(self.open_settings_dialog)
        btn_row.addWidget(btn_settings, 1)

        server_layout.addLayout(btn_row)
        sidebar_layout.addWidget(server_panel)

        root_layout.addWidget(sidebar)

        # ── Right Side (Stacked Tab Pages) ──────────────────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        root_layout.addWidget(right_widget, 1)

        self.tabs = QStackedWidget()
        right_layout.addWidget(self.tabs)

        self.tab_installed = QWidget()
        self.tab_presets = QWidget()
        self.tab_browse = QWidget()
        self.tab_installer = QWidget()
        self.tab_performance = QWidget()

        self.tabs.addWidget(self.tab_installed)
        self.tabs.addWidget(self.tab_presets)
        self.tabs.addWidget(self.tab_browse)
        self.tabs.addWidget(self.tab_installer)
        self.tabs.addWidget(self.tab_performance)

        installed_tab.setup_installed_tab(self)
        presets_tab.setup_presets_tab(self)
        browse_tab.setup_browse_tab(self)
        installer_tab.setup_installer_tab(self)
        performance_tab.setup_performance_tab(self)

        # Wire navigation buttons to switch stacked widget
        for idx, btn in enumerate(self.nav_buttons):
            btn.clicked.connect(lambda _checked, i=idx: self.tabs.setCurrentIndex(i))

    # ------------------ Process & Server Controls ------------------

    def check_server_status(self):
        running = is_server_running()
        if running:
            server_ip_port = "127.0.0.1:6969"
            try:
                cfg = load_config()
                spt_root = Path(cfg.get("spt_path", str(find_spt_root()))).resolve()
                http_cfg_path = spt_root / "SPT_Runtime" / "SPT_Data" / "configs" / "http.json"
                if http_cfg_path.exists():
                    with open(http_cfg_path, encoding="utf-8") as f:
                        data = json.load(f)
                        ip = data.get("ip", "127.0.0.1")
                        port = data.get("port", 6969)
                        server_ip_port = f"{ip}:{port}"
            except Exception:
                pass

            if hasattr(self, "server_dot"):
                self.server_dot.setStyleSheet(f"color: {SUCCESS}; font-size: 13px;")
            if hasattr(self, "server_status_lbl"):
                self.server_status_lbl.setText(f"Running ({server_ip_port})")
                self.server_status_lbl.setStyleSheet(f"color: {SUCCESS}; font-weight: 600;")
            if hasattr(self, "btn_server_control"):
                self.btn_server_control.setText("Stop")
                self.btn_server_control.setProperty("role", "danger")
                self.btn_server_control.style().unpolish(self.btn_server_control)
                self.btn_server_control.style().polish(self.btn_server_control)
        else:
            if hasattr(self, "server_dot"):
                self.server_dot.setStyleSheet(f"color: {DANGER}; font-size: 13px;")
            if hasattr(self, "server_status_lbl"):
                self.server_status_lbl.setText("Stopped")
                self.server_status_lbl.setStyleSheet(f"color: {DANGER}; font-weight: 600;")
            if hasattr(self, "btn_server_control"):
                self.btn_server_control.setText("Start")
                self.btn_server_control.setProperty("role", "success")
                self.btn_server_control.style().unpolish(self.btn_server_control)
                self.btn_server_control.style().polish(self.btn_server_control)

    def toggle_server_control(self):
        if is_server_running():
            stop_server()
            self.toast.error("🛑 Stopping SPT Server...")
            QTimer.singleShot(500, self.check_server_status)
        else:
            cfg = load_config()
            spt_root = Path(cfg.get("spt_path", str(find_spt_root()))).resolve()
            server_script = Path(cfg.get("server_script", str(spt_root / "server.sh")))
            server_binary = spt_root / "SPT_Runtime" / "SPT.Server.Linux"

            env = os.environ.copy()
            env.pop("LD_LIBRARY_PATH", None)

            launched = False
            if server_script.exists():
                try:
                    subprocess.Popen(
                        [str(server_script)], cwd=str(server_script.parent), env=env, start_new_session=True
                    )
                    launched = True
                except Exception as e:
                    print(f"Failed launching server.sh: {e}")

            if not launched and server_binary.exists():
                try:
                    subprocess.Popen(
                        [str(server_binary)], cwd=str(server_binary.parent), env=env, start_new_session=True
                    )
                    launched = True
                except Exception as e:
                    print(f"Failed launching SPT.Server.Linux directly: {e}")

            if launched:
                self.toast.success("🚀 Starting SPT Server...")
            else:
                self.show_missing_script_dialog("server.sh", server_script)

            QTimer.singleShot(1500, self.check_server_status)

    def launch_spt(self):
        cfg = load_config()
        spt_root = Path(cfg.get("spt_path", str(find_spt_root()))).resolve()
        launcher_script = Path(cfg.get("launcher_script", str(spt_root / "launcher.sh")))
        if launcher_script.exists():
            subprocess.Popen([str(launcher_script)], cwd=str(launcher_script.parent))
            self.toast.success(f"🚀 Launching SPT via {launcher_script.name}...")
        else:
            self.show_missing_script_dialog("launcher.sh", launcher_script)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            cfg = load_config()
            spt_root = Path(cfg["spt_path"]).resolve()
            apply_spt_root(spt_root)

            self.installed_spt_ver = detect_installed_spt_version()
            self.load_installed_mods()
            self.toast.success("💾 Settings saved and applied!")

    def show_toast(
        self,
        text,
        duration_ms=2500,
        bg_color="#181825",
        border_color="#89b4fa",
        text_color="#cdd6f4",
    ):
        """Compatibility wrapper for toast notifications."""
        self.toast._show(text, border_color, duration_ms)

    def show_missing_script_dialog(self, script_name, script_path):
        QMessageBox.warning(
            self,
            "⚠️ Script Not Found",
            f"The script <code>{script_name}</code> could not be found at:\n\n"
            f"<code>{script_path}</code>\n\n"
            f"Please update your paths in ⚙️ Settings.",
        )

    # installed_tab bindings
    _set_chip_filter = installed_tab._set_chip_filter
    _on_mod_row_checked = installed_tab._on_mod_row_checked
    load_installed_mods = installed_tab.load_installed_mods
    render_installed_mods = installed_tab.render_installed_mods
    on_fika_updated = installed_tab.on_fika_updated
    on_installed_table_cell_clicked = installed_tab.on_installed_table_cell_clicked
    show_installed_table_context_menu = installed_tab.show_installed_table_context_menu
    check_installed_mod_updates = installed_tab.check_installed_mod_updates
    update_bulk_actions_bar = installed_tab.update_bulk_actions_bar
    get_selected_installed_mods = installed_tab.get_selected_installed_mods
    select_all_installed_mods = installed_tab.select_all_installed_mods
    deselect_all_installed_mods = installed_tab.deselect_all_installed_mods
    bulk_enable_selected = installed_tab.bulk_enable_selected
    bulk_disable_selected = installed_tab.bulk_disable_selected
    bulk_delete_selected = installed_tab.bulk_delete_selected
    filter_installed_mods = installed_tab.filter_installed_mods
    toggle_mod = installed_tab.toggle_mod
    audit_installed_dependencies = installed_tab.audit_installed_dependencies
    show_audit_issues_dialog = installed_tab.show_audit_issues_dialog
    open_author_profile = installed_tab.open_author_profile
    open_mod_folder = installed_tab.open_mod_folder
    open_mod_web = installed_tab.open_mod_web
    delete_mod = installed_tab.delete_mod

    # presets_tab bindings
    export_stash_manifest = presets_tab.export_stash_manifest
    import_stash_manifest = presets_tab.import_stash_manifest
    load_presets_list = presets_tab.load_presets_list
    on_preset_selected = presets_tab.on_preset_selected
    create_preset_from_stash = presets_tab.create_preset_from_stash
    apply_selected_preset = presets_tab.apply_selected_preset
    export_selected_preset = presets_tab.export_selected_preset
    import_preset_file = presets_tab.import_preset_file
    delete_selected_preset = presets_tab.delete_selected_preset

    # browse_tab bindings
    fetch_remote_mods = browse_tab.fetch_remote_mods
    on_remote_mods_fetched = browse_tab.on_remote_mods_fetched
    filter_remote_mods = browse_tab.filter_remote_mods
    render_mod_detail_html = browse_tab.render_mod_detail_html
    on_remote_mod_selected = browse_tab.on_remote_mod_selected
    on_dependencies_fetched = browse_tab.on_dependencies_fetched
    start_mod_download = browse_tab.start_mod_download
    execute_single_mod_download = browse_tab.execute_single_mod_download
    start_dependency_queue_download = browse_tab.start_dependency_queue_download
    process_next_dependency_in_queue = browse_tab.process_next_dependency_in_queue
    on_dependency_downloaded = browse_tab.on_dependency_downloaded
    on_dependency_installed = browse_tab.on_dependency_installed
    on_mod_downloaded = browse_tab.on_mod_downloaded
    open_mod_in_browser = browse_tab.open_mod_in_browser

    # installer_tab bindings
    open_file_installer = installer_tab.open_file_installer
    on_mod_installed = installer_tab.on_mod_installed

    # performance_tab bindings
    save_and_apply_performance_settings = performance_tab.save_and_apply_performance_settings
    auto_detect_cpu_allocation_ui = performance_tab.auto_detect_cpu_allocation_ui


def main():
    """Application entry point."""
    import sys

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    # High-DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    ensure_dirs()
    apply_spt_root(find_spt_root())

    app = QApplication(sys.argv)
    app.setStyleSheet(get_app_stylesheet())
    window = SPTModManagerWindow()
    window.show()
    sys.exit(app.exec())
