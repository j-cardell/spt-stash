#!/usr/bin/env python3
"""SPT Stash — main application window with V4 modern sidebar navigation."""

import html
import json
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import paths
from ..catalog.updates import AppUpdateChecker
from ..config import load_config
from ..paths import apply_spt_root, ensure_dirs, find_app_icon, find_spt_root
from ..system.hardware import detect_installed_spt_version
from ..system.process import (
    is_server_running,
    launch_spt_launcher,
    log_tail,
    perf_launch_spec,
    running_client_apps,
    stop_server,
)
from ..version import __version__
from .dialogs import SettingsDialog
from .styles import get_app_stylesheet
from .tabs import browse as browse_tab
from .tabs import installed as installed_tab
from .tabs import installer as installer_tab
from .tabs import performance as performance_tab
from .tabs import presets as presets_tab
from .theme import ACCENT, BG, BORDER, DANGER, SUCCESS, SURFACE_2, TEXT, TEXT_MUTED, TOAST_BG, TOAST_BORDER, TOAST_TEXT
from .toast import ToastManager
from .widgets import _nav_pixmap


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

        self._check_for_app_update()

    def _check_for_app_update(self):
        if not load_config().get("check_app_updates", True):  # opt out: set to false in config.json
            return
        self.update_checker = AppUpdateChecker(self)
        self.update_checker.found.connect(self._on_app_update_found)
        self.update_checker.start()

    def _on_app_update_found(self, tag, url):
        self.btn_update.setText(f"Update available: {tag}")
        self.btn_update.setToolTip(f"You have v{__version__}. Click to open the {tag} release page.")
        self.btn_update.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        self.btn_update.show()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        root_layout = QHBoxLayout(main_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(8, 16, 8, 8)
        sidebar_layout.setSpacing(4)

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
            ("installed", "Installed", "tab_installed"),
            ("presets", "Presets", "tab_presets"),
            ("browse", "Browse Forge", "tab_browse"),
            ("install", "Install", "tab_installer"),
            ("performance", "Performance", "tab_performance"),
        ]
        self.nav_buttons = []
        for idx, (icon_name, label, _attr) in enumerate(nav_items):
            btn = QPushButton(label)
            btn.setProperty("nav", "true")
            btn.setIcon(QIcon(_nav_pixmap(icon_name, size=16, color=TEXT_MUTED)))
            btn.setIconSize(QSize(16, 16))
            btn.setCheckable(True)
            if idx == 0:
                btn.setChecked(True)
            self.nav_group.addButton(btn)
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        # Apply accent icon color to checked nav buttons after stylesheet is known.
        def _refresh_nav_icons():
            for b, (icon_name, _, _) in zip(self.nav_buttons, nav_items):
                color = ACCENT if b.isChecked() else TEXT_MUTED
                b.setIcon(QIcon(_nav_pixmap(icon_name, size=16, color=color)))
        for b in self.nav_buttons:
            b.toggled.connect(_refresh_nav_icons)
        _refresh_nav_icons()

        sidebar_layout.addStretch()

        # Shown only when a newer release exists on GitHub (see _check_for_app_update)
        self.btn_update = QPushButton("")
        self.btn_update.setProperty("role", "ghost")
        self.btn_update.setProperty("size", "sm")
        self.btn_update.setStyleSheet(f"color: {SUCCESS};")
        self.btn_update.hide()
        sidebar_layout.addWidget(self.btn_update)

        # Server Control Panel at bottom of sidebar
        server_panel = QFrame()
        server_panel.setObjectName("serverPanel")
        server_layout = QVBoxLayout(server_panel)
        server_layout.setContentsMargins(8, 10, 8, 8)
        server_layout.setSpacing(8)

        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self.server_dot = QLabel("")
        self.server_dot.setStyleSheet(f"color: {DANGER}; font-size: 13px;")
        status_row.addWidget(self.server_dot)
        self.server_status_lbl = QLabel("Server: Stopped")
        self.server_status_lbl.setObjectName("serverStatus")
        status_row.addWidget(self.server_status_lbl)
        status_row.addStretch()
        server_layout.addLayout(status_row)

        self.btn_launch = QPushButton(" Launch SPT")
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

        btn_settings = QPushButton(" Settings")
        btn_settings.setProperty("role", "ghost")
        btn_settings.setProperty("size", "sm")
        btn_settings.clicked.connect(self.open_settings_dialog)
        btn_row.addWidget(btn_settings, 1)

        server_layout.addLayout(btn_row)
        sidebar_layout.addWidget(server_panel)

        root_layout.addWidget(sidebar)

        #  Right Side (Stacked Tab Pages)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        root_layout.addWidget(right_widget, 1)

        self.tabs = QStackedWidget()
        right_layout.addWidget(self.tabs)

        # Global download strip: visible from every tab (presets/updates download while you're elsewhere).
        self.dl_frame = QFrame()
        self.dl_frame.setStyleSheet(f"QFrame {{ background: {SURFACE_2}; border-top: 1px solid {BORDER}; }}")
        dl_layout = QHBoxLayout(self.dl_frame)
        dl_layout.setContentsMargins(16, 6, 16, 6)
        self.dl_label = QLabel("")
        self.dl_label.setStyleSheet(f"color: {TEXT}; font-size: 12px; border: none;")
        dl_layout.addWidget(self.dl_label, 1)
        self.dl_bar = QProgressBar()
        self.dl_bar.setRange(0, 100)
        self.dl_bar.setFixedWidth(260)
        self.dl_bar.setStyleSheet(
            f"QProgressBar {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 4px; "
            f"text-align: center; color: {TEXT}; }} QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}"
        )
        dl_layout.addWidget(self.dl_bar)
        self.dl_frame.hide()
        right_layout.addWidget(self.dl_frame)

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
        # Bind installed-tab helpers into MainWindow namespace before cell widgets wire their signals
        self.show_installed_mod_detail = installed_tab.show_installed_mod_detail.__get__(self, type(self))
        self.on_installed_table_cell_clicked = getattr(
            installed_tab, "on_installed_table_cell_clicked", lambda r, c: None
        ).__get__(self, type(self))
        presets_tab.setup_presets_tab(self)
        browse_tab.setup_browse_tab(self)
        # Bind installer helpers into MainWindow namespace before setup wires buttons
        self.start_local_install = installer_tab.start_local_install.__get__(self, type(self))
        self.clear_local_install = installer_tab.clear_local_install.__get__(self, type(self))
        self.set_install_archive = installer_tab.set_install_archive.__get__(self, type(self))
        self._on_install_drop = installer_tab._on_install_drop.__get__(self, type(self))
        installer_tab.setup_installer_tab(self)
        performance_tab.setup_performance_tab(self)

        # Wire navigation buttons to switch stacked widget
        for idx, btn in enumerate(self.nav_buttons):
            btn.clicked.connect(lambda _checked, i=idx: self.tabs.setCurrentIndex(i))

    # ------------------ Process & Server Controls ------------------

    def show_download_progress(self, label, percent=None):
        """percent=None shows a busy (indeterminate) bar, used while archives are being extracted/staged."""
        self.dl_label.setText(label)
        if percent is None:
            self.dl_bar.setRange(0, 0)
        else:
            self.dl_bar.setRange(0, 100)
            self.dl_bar.setValue(max(0, min(100, int(percent))))
        self.dl_frame.show()

    def hide_download_progress(self):
        self.dl_frame.hide()

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

    def _await_server_stop(self, attempts):
        """Poll every 250ms until the server process is gone, then refresh the badge and confirm."""
        self.check_server_status()
        if not is_server_running():
            self.toast.success("SPT Server stopped")
        elif attempts > 0:
            QTimer.singleShot(250, lambda: self._await_server_stop(attempts - 1))
        else:
            self.toast.error("Server did not stop in 10s")

    def toggle_server_control(self):
        if is_server_running():
            open_apps = running_client_apps()
            if open_apps:
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Warning)
                box.setWindowTitle("Close the Launcher First")
                box.setText(
                    f"<b>{' and '.join(open_apps)}</b> is still open and connected to the server.<br><br>"
                    "Close it before stopping the server, otherwise the server can hang while shutting down "
                    "and may have to be force-killed, which can lose unsaved profile progress."
                )
                box.addButton("Stop Anyway", QMessageBox.DestructiveRole)
                cancel = box.addButton("Cancel", QMessageBox.RejectRole)
                box.setDefaultButton(cancel)
                box.exec()
                if box.clickedButton() is cancel:
                    return
            self._server_stop_requested = True
            stop_server()
            self.toast.error(" Stopping SPT Server...")
            self._await_server_stop(attempts=40)
        else:
            cfg = load_config()
            spt_root = Path(cfg.get("spt_path", str(find_spt_root()))).resolve()
            server_script = Path(cfg.get("server_script", str(spt_root / "server.sh")))
            server_binary = spt_root / "SPT_Runtime" / "SPT.Server.Linux"

            env = os.environ.copy()
            env.pop("LD_LIBRARY_PATH", None)
            pfx, extra_env = perf_launch_spec(cfg, "server")
            env.update(extra_env)

            self._server_stop_requested = False
            log = open(paths.SERVER_LOG, "wb")
            popen_kw = {"env": env, "start_new_session": True, "stdin": subprocess.DEVNULL, "stdout": log, "stderr": log}
            proc = None
            launched = False
            if server_script.exists():
                try:
                    proc = subprocess.Popen([*pfx, str(server_script)], cwd=str(server_script.parent), **popen_kw)
                    launched = True
                except Exception as e:
                    print(f"Failed launching server.sh: {e}")

            if not launched and server_binary.exists():
                try:
                    proc = subprocess.Popen([*pfx, str(server_binary)], cwd=str(server_binary.parent), **popen_kw)
                    launched = True
                except Exception as e:
                    print(f"Failed launching SPT.Server.Linux directly: {e}")

            log.close()  # the child keeps its own handle
            if launched:
                self.toast.success("Starting SPT Server...")
                self._watch_server_start(proc)
            else:
                self.show_missing_script_dialog("server.sh", server_script)

            QTimer.singleShot(1500, self.check_server_status)

    def _watch_server_start(self, proc, attempts=20):
        """If the server we just started dies within ~20s (and we didn't stop it), show why."""
        if proc.poll() is None:
            if attempts > 0:
                QTimer.singleShot(1000, lambda: self._watch_server_start(proc, attempts - 1))
            return
        if getattr(self, "_server_stop_requested", False):
            return
        tail = html.escape(log_tail(paths.SERVER_LOG))
        QMessageBox.critical(
            self,
            "SPT Server stopped right after starting",
            f"The server exited (code {proc.returncode}). Last lines of its output:<br><br>"
            f"<pre>{tail or '(no output)'}</pre><br>"
            f"Full log: <code>{paths.SERVER_LOG}</code><br>"
            "A mod that fails to load is the usual cause. Disable the mod named in the error and start again.",
        )

    def launch_spt(self):
        cfg = load_config()
        spt_root = Path(cfg.get("spt_path", str(find_spt_root()))).resolve()
        launcher_script = Path(cfg.get("launcher_script", str(spt_root / "launcher.sh")))
        if launcher_script.exists():
            pfx, env = perf_launch_spec(cfg, "client")
            launch_spt_launcher(launcher_script, env_overrides=env, cmd_prefix=pfx)
            self.toast.success(f"Launching SPT via {launcher_script.name}...")
        else:
            self.show_missing_script_dialog("launcher.sh", launcher_script)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            cfg = load_config()
            spt_root = Path(cfg["spt_path"]).resolve()
            apply_spt_root(spt_root, cfg.get("staged_dir"))
            ensure_dirs()

            self.installed_spt_ver = detect_installed_spt_version()
            self.load_installed_mods()
            self.toast.success("Settings saved and applied!")

    def show_toast(
        self,
        text,
        duration_ms=2500,
        bg_color=TOAST_BG,
        border_color=TOAST_BORDER,
        text_color=TOAST_TEXT,
    ):
        """Compatibility wrapper for toast notifications."""
        self.toast._show(text, border_color, duration_ms)

    def show_missing_script_dialog(self, script_name, script_path):
        QMessageBox.warning(
            self,
            "Script Not Found",
            f"The script <code>{script_name}</code> could not be found at:\n\n"
            f"<code>{script_path}</code>\n\n"
            f"Please update your paths in Settings.",
        )

    def closeEvent(self, event):
        """Stop background timers/threads so the process exits cleanly."""
        self.status_timer.stop()
        rss_thread = getattr(self, "rss_thread", None)
        if rss_thread and rss_thread.isRunning():
            rss_thread.terminate()
            rss_thread.wait(3000)
        event.accept()

    # installed_tab bindings
    _set_chip_filter = installed_tab._set_chip_filter
    _on_mod_row_checked = installed_tab._on_mod_row_checked
    load_installed_mods = installed_tab.load_installed_mods
    render_installed_mods = installed_tab.render_installed_mods
    on_fika_updated = installed_tab.on_fika_updated
    _render_installed_detail_html = installed_tab._render_installed_detail_html
    _on_full_description_fetched = installed_tab._on_full_description_fetched

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
    on_remote_mod_installed = browse_tab.on_remote_mod_installed
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

    cfg = load_config()
    apply_spt_root(cfg.get("spt_path") or find_spt_root(), cfg.get("staged_dir"))
    ensure_dirs()

    app = QApplication(sys.argv)
    app.setStyleSheet(get_app_stylesheet())
    window = SPTModManagerWindow()
    window.show()
    sys.exit(app.exec())
