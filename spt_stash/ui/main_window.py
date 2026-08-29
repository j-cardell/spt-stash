#!/usr/bin/env python3
"""SPT Stash — main application window."""

import json
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import load_config
from ..paths import apply_spt_root, ensure_dirs, find_spt_root
from ..system.hardware import detect_installed_spt_version
from ..system.process import is_server_running, stop_server
from .dialogs import SettingsDialog
from .tabs import browse as browse_tab
from .tabs import installed as installed_tab
from .tabs import installer as installer_tab
from .tabs import performance as performance_tab
from .tabs import presets as presets_tab
from .widgets import ToastNotification


def _indent(text, prefix):
    return "\n".join(prefix + line if line.strip() else line for line in text.split("\n"))


class SPTModManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SPT Stash — Mod Manager for Single-Player Tarkov")
        self.resize(1150, 720)

        # Style
        self.setStyleSheet("""
                QMainWindow {
                    background-color: #1e1e2e;
                    color: #cdd6f4;
                }
                QWidget {
                    background-color: #1e1e2e;
                    color: #cdd6f4;
                    font-family: 'Segoe UI', Ubuntu, sans-serif;
                    font-size: 13px;
                }
                QGroupBox {
                    border: 1px solid #45475a;
                    border-radius: 8px;
                    margin-top: 10px;
                    padding-top: 10px;
                    font-weight: bold;
                    color: #cba6f7;
                }
                QTabWidget::pane {
                    border: 1px solid #313244;
                    background: #181825;
                    border-radius: 6px;
                }
                QTabBar::tab {
                    background: #313244;
                    color: #a6adc8;
                    padding: 8px 18px;
                    margin-right: 4px;
                    border-top-left-radius: 6px;
                    border-top-right-radius: 6px;
                    font-weight: bold;
                }
                QTabBar::tab:selected {
                    background: #89b4fa;
                    color: #11111b;
                }
                QPushButton {
                    background-color: #313244;
                    border: 1px solid #45475a;
                    color: #cdd6f4;
                    padding: 6px 14px;
                    border-radius: 6px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #45475a;
                    border-color: #585b70;
                }
                QPushButton#btnLaunch {
                    background-color: #27392b;
                    color: #a6e3a1;
                    border: 1px solid #36503c;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton#btnLaunch:hover {
                    background-color: #314a38;
                    border-color: #a6e3a1;
                }
                QPushButton#btnStop {
                    background-color: #3a232e;
                    color: #f38ba8;
                    border: 1px solid #542f3e;
                    font-weight: bold;
                }
                QPushButton#btnStop:hover {
                    background-color: #4a2c3b;
                    border-color: #f38ba8;
                }
                QLineEdit, QComboBox {
                    background-color: #313244;
                    border: 1px solid #45475a;
                    color: #cdd6f4;
                    padding: 6px;
                    border-radius: 6px;
                }
                QTableWidget, QListWidget {
                    background-color: #181825;
                    border: 1px solid #313244;
                    gridline-color: #313244;
                    border-radius: 6px;
                }
                QHeaderView::section {
                    background-color: #313244;
                    color: #cdd6f4;
                    padding: 6px;
                    border: none;
                    font-weight: bold;
                }
                QTextBrowser {
                    background-color: #181825;
                    border: 1px solid #313244;
                    border-radius: 6px;
                    color: #cdd6f4;
                }
            """)

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
        main_layout = QVBoxLayout(main_widget)

        # Header Bar
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        icon_path = Path(__file__).parent / "docs" / "spt_stash_icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
            lbl_icon = QLabel()
            pixmap = QPixmap(str(icon_path)).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl_icon.setPixmap(pixmap)
            header_layout.addWidget(lbl_icon)

        title_label = QLabel("SPT Stash")
        title_label.setFont(QFont("Ubuntu", 17, QFont.Bold))
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.status_badge = QLabel("Server: Unknown")
        self.status_badge.setStyleSheet(
            "padding: 4px 10px; border-radius: 12px; background-color: #45475a; font-weight: bold;"
        )
        header_layout.addWidget(self.status_badge)

        self.btn_server_control = QPushButton("▶ Start Server")
        self.btn_server_control.clicked.connect(self.toggle_server_control)
        header_layout.addWidget(self.btn_server_control)

        self.btn_launch = QPushButton("▶ Launch SPT")
        self.btn_launch.setObjectName("btnLaunch")
        self.btn_launch.clicked.connect(self.launch_spt)
        header_layout.addWidget(self.btn_launch)

        self.btn_settings = QPushButton("⚙️ Settings")
        self.btn_settings.clicked.connect(self.open_settings_dialog)
        header_layout.addWidget(self.btn_settings)

        main_layout.addLayout(header_layout)

        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.tab_installed = QWidget()
        self.tab_presets = QWidget()
        self.tab_browse = QWidget()
        self.tab_installer = QWidget()
        self.tab_performance = QWidget()

        self.tabs.addTab(self.tab_installed, "Installed Mods")
        self.tabs.addTab(self.tab_presets, "🎒 Presets && Manifests")
        self.tabs.addTab(self.tab_browse, "Browse sp-mod.com (Forge)")
        self.tabs.addTab(self.tab_installer, "Install Local Mod Archive")
        self.tabs.addTab(self.tab_performance, "⚡ Linux Performance")

        installed_tab.setup_installed_tab(self)
        presets_tab.setup_presets_tab(self)
        browse_tab.setup_browse_tab(self)
        installer_tab.setup_installer_tab(self)
        performance_tab.setup_performance_tab(self)

    # ------------------ Installed Mods Tab ------------------

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

            if hasattr(self, "status_badge"):
                self.status_badge.setText(f"🟢 Server: Running ({server_ip_port})")
                self.status_badge.setStyleSheet(
                    "padding: 4px 10px; border-radius: 12px; background-color: #a6e3a1; color: #11111b; font-weight: bold;"
                )
            if hasattr(self, "btn_server_control"):
                self.btn_server_control.setText("🛑 Stop Server")
                self.btn_server_control.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold;")
        else:
            if hasattr(self, "status_badge"):
                self.status_badge.setText("🔴 Server: Stopped")
                self.status_badge.setStyleSheet(
                    "padding: 4px 10px; border-radius: 12px; background-color: #f38ba8; color: #11111b; font-weight: bold;"
                )
            if hasattr(self, "btn_server_control"):
                self.btn_server_control.setText("▶ Start Server")
                self.btn_server_control.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold;")

    def toggle_server_control(self):
        if is_server_running():
            stop_server()
            self.show_toast(
                "🛑 Stopping SPT Server...",
                border_color="#f38ba8",
                text_color="#f38ba8",
            )
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
                self.show_toast(
                    "🚀 Starting SPT Server...",
                    border_color="#a6e3a1",
                    text_color="#a6e3a1",
                )
            else:
                self.show_missing_script_dialog("server.sh", server_script)

            QTimer.singleShot(1500, self.check_server_status)

    def launch_spt(self):
        cfg = load_config()
        spt_root = Path(cfg.get("spt_path", str(find_spt_root()))).resolve()
        launcher_script = Path(cfg.get("launcher_script", str(spt_root / "launcher.sh")))
        if launcher_script.exists():
            subprocess.Popen([str(launcher_script)], cwd=str(launcher_script.parent))
            self.show_toast(
                f"🚀 Launching SPT via {launcher_script.name}...",
                border_color="#a6e3a1",
                text_color="#a6e3a1",
            )
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
            self.show_toast(
                "💾 Settings saved and applied!",
                border_color="#a6e3a1",
                text_color="#a6e3a1",
            )

    def show_toast(
        self,
        text,
        duration_ms=2200,
        bg_color="#181825",
        border_color="#89b4fa",
        text_color="#cdd6f4",
    ):
        if not hasattr(self, "_toast"):
            self._toast = ToastNotification(self)
        self._toast.show_message(text, duration_ms, bg_color, border_color, text_color)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_toast") and self._toast.isVisible():
            p_rect = self.rect()
            x = (p_rect.width() - self._toast.width()) // 2
            y = p_rect.height() - self._toast.height() - 36
            self._toast.move(max(10, x), max(10, y))

    def show_missing_script_dialog(self, script_name, script_path):
        QMessageBox.warning(
            self,
            "⚠️ Script Not Found",
            f"The script <code>{script_name}</code> could not be found at:\n\n"
            f"<code>{script_path}</code>\n\n"
            f"Please update your paths in ⚙️ Settings.",
        )

    # installed_tab bindings
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

    from PySide6.QtWidgets import QApplication

    ensure_dirs()
    apply_spt_root(find_spt_root())

    app = QApplication(sys.argv)
    window = SPTModManagerWindow()
    window.show()
    sys.exit(app.exec())
