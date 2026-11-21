#!/usr/bin/env python3
"""SPT Stash — application dialogs (Settings, StageInstall, SavePreset) with V4 styling."""

import logging
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from PySide6.QtCore import QSize, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ..catalog.dependencies import is_dependency_installed
from ..config import load_config, save_config
from ..paths import DOWNLOADS_CACHE_DIR
from ..staging.links import create_relative_symlink
from ..system.hardware import find_umu_run, find_wine_prefix, get_available_proton_versions
from .theme import (
    ACCENT,
    BG,
    BORDER,
    BTN_HOVER_BORDER,
    DANGER,
    SUCCESS,
    SURFACE,
    SURFACE_2,
    TEXT,
    TEXT_MUTED,
)
from .widgets import _nav_pixmap

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings — SPT Stash")
        self.resize(680, 480)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {BG}; color: {TEXT}; }}
            QLabel {{ color: {TEXT}; font-size: 13px; }}
            QLineEdit {{ background-color: {SURFACE}; border: 1px solid {BORDER}; color: {TEXT}; padding: 7px 10px; border-radius: 6px; }}
            QLineEdit:focus {{ border-color: {ACCENT}; }}
            QPushButton {{ background-color: {SURFACE_2}; border: 1px solid {BORDER}; color: {TEXT}; padding: 6px 14px; border-radius: 6px; }}
            QPushButton:hover {{ background-color: {BORDER}; border-color: {BTN_HOVER_BORDER}; }}
            QComboBox {{ background-color: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px 10px; border-radius: 6px; }}
            QComboBox QAbstractItemView {{ background-color: {SURFACE}; color: {TEXT}; selection-background-color: {BORDER}; border: 1px solid {BORDER}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.cfg = load_config()

        def _row(label_text, help_text, line_edit, browse_handler):
            lbl = QLabel(f"<b>{label_text}</b>")
            help_lbl = QLabel(f"<small style='color: {TEXT_MUTED};'>{help_text}</small>")
            help_lbl.setWordWrap(True)
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(line_edit)
            btn = QPushButton("Browse...")
            btn.setProperty("role", "ghost")
            btn.setProperty("size", "sm")
            btn.clicked.connect(browse_handler)
            row.addWidget(btn)
            layout.addWidget(lbl)
            layout.addWidget(help_lbl)
            layout.addLayout(row)

        self.txt_spt = QLineEdit(self.cfg.get("spt_path", ""))
        self.txt_spt.setToolTip(
            "Select the root directory where Single-Player Tarkov (SPT) is installed (e.g. ~/Games/SPT)."
        )
        _row(
            "SPT Installation Folder:",
            "Root directory containing server.sh, launcher.sh, BepInEx, and SPT_Runtime (e.g. ~/Games/SPT).",
            self.txt_spt,
            self.browse_spt_folder,
        )

        self.txt_staged = QLineEdit(self.cfg.get("staged_dir", ""))
        self.txt_staged.setToolTip("Directory where SPT Stash stores downloaded and extracted mod files.")
        _row(
            "Mod Staging Stash Directory:",
            "Local directory where SPT Stash downloads and stages mods before symlinking into the game.",
            self.txt_staged,
            self.browse_staged_folder,
        )

        self.txt_server = QLineEdit(self.cfg.get("server_script", ""))
        self.txt_server.setToolTip("Executable path to server.sh or SPT.Server.exe.")
        _row(
            "Start Server Script Path:",
            "Path to server.sh (or SPT.Server.exe) used to launch the SPT server process.",
            self.txt_server,
            self.browse_server_script,
        )

        self.txt_launcher = QLineEdit(self.cfg.get("launcher_script", ""))
        self.txt_launcher.setToolTip("Executable path to launcher.sh or SPT.Launcher.exe.")
        _row(
            "Launch SPT / Launcher Script Path:",
            "Path to launcher.sh (or SPT.Launcher.exe) used to launch the game.",
            self.txt_launcher,
            self.browse_launcher_script,
        )

        lbl_proton = QLabel("<b>Proton / Compatibility Runner:</b>")
        help_proton = QLabel(
            f"<small style='color: {TEXT_MUTED};'>Select which Proton/Proton-GE runner executes "
            "Greed.exe (SVM) and Windows components.</small>"
        )
        help_proton.setWordWrap(True)
        self.combo_proton = QComboBox()

        saved_proton = self.cfg.get("proton_runner", "auto")
        available_protons = get_available_proton_versions()
        for p_info in available_protons:
            self.combo_proton.addItem(p_info["label"], p_info["id"])

        idx = self.combo_proton.findData(saved_proton)
        if idx >= 0:
            self.combo_proton.setCurrentIndex(idx)

        layout.addWidget(lbl_proton)
        layout.addWidget(help_proton)
        layout.addWidget(self.combo_proton)

        layout.addSpacing(6)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        btn_desktop = QPushButton("Create Desktop Shortcut")
        btn_desktop.setIcon(QIcon(_nav_pixmap("install", size=14, color=TEXT_MUTED)))
        btn_desktop.setIconSize(QSize(14, 14))
        btn_desktop.setProperty("role", "ghost")
        btn_desktop.setProperty("size", "sm")
        btn_desktop.clicked.connect(self.create_desktop_shortcut)
        btn_box.addWidget(btn_desktop)

        btn_greed = QPushButton("Launch Greed.exe (SVM)")
        btn_greed.setIcon(QIcon(_nav_pixmap("performance", size=14, color=TEXT_MUTED)))
        btn_greed.setIconSize(QSize(14, 14))
        btn_greed.setProperty("role", "ghost")
        btn_greed.setProperty("size", "sm")
        btn_greed.setToolTip(
            "Launch Greed.exe (SVM Configurator) safely inside your SPT Wine Prefix (~/Games/SPT-Prefix)."
        )
        btn_greed.clicked.connect(self.launch_greed_exe)
        btn_box.addWidget(btn_greed)

        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setProperty("role", "ghost")
        btn_cancel.setProperty("size", "sm")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("Save Settings")
        btn_save.setIcon(QIcon(_nav_pixmap("installed", size=14, color=BG)))
        btn_save.setIconSize(QSize(14, 14))
        btn_save.setProperty("role", "primary")
        btn_save.setProperty("size", "sm")
        btn_save.clicked.connect(self.save_settings)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def create_desktop_shortcut(self):
        try:
            from install_desktop_shortcut import install_desktop_shortcut

            install_desktop_shortcut()
            QMessageBox.information(
                self,
                "Desktop Shortcut Created",
                "Desktop Shortcut & Application Launcher Created!</br></br>You can now "
                "launch <b>SPT Stash</b> directly from your Linux Desktop or Application Menu.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error Creating Shortcut", f"Failed to create desktop shortcut: {e}")

    def launch_greed_exe(self):
        spt_root = Path(self.txt_spt.text()).resolve()

        staged_server = spt_root / ".staged" / "server"
        live_server = spt_root / "SPT_Runtime" / "user" / "mods"

        # 1. Locate SVM in staged or live folders
        staged_svm = staged_server / "[SVM] Server Value Modifier"
        live_svm = live_server / "[SVM] Server Value Modifier"

        if not staged_svm.exists() and staged_server.exists():
            for d in staged_server.iterdir():
                if d.is_dir() and (d / "Greed.exe").exists():
                    staged_svm = d
                    live_svm = live_server / d.name
                    break

        if staged_svm.exists() and not live_svm.exists():
            create_relative_symlink(staged_svm, live_svm)

        # 2. Ensure Greed.exe is in the root SPT folder
        greed_root = spt_root / "Greed.exe"
        if not greed_root.exists():
            for c in (live_svm / "Greed.exe", staged_svm / "Greed.exe"):
                if c.exists():
                    try:
                        shutil.copy2(c, greed_root)
                    except Exception:
                        pass
                    break

        if not greed_root.exists():
            reply = QMessageBox.question(
                self,
                "SVM Not Installed",
                "Greed.exe was not found in your SPT installation.\n\n"
                "Would you like to open the <b>Browse sp-mod.com (Forge)</b> tab to download <b>Server Value Modifier (SVM)</b>?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.accept()
                parent = self.parent()
                if parent and hasattr(parent, "tabs"):
                    parent.tabs.setCurrentIndex(2)
                    if hasattr(parent, "browse_search"):
                        parent.browse_search.setText("Server Value Modifier")
            return

        prefix_path = find_wine_prefix(spt_root)
        available_protons = get_available_proton_versions()
        selected_runner = self.combo_proton.currentData() if hasattr(self, "combo_proton") else self.cfg.get("proton_runner", "auto")

        proton_path = None
        if selected_runner == "auto":
            for p in available_protons:
                if p["id"] == "auto":
                    proton_path = Path(p["path"])
                    break
        elif selected_runner != "wine":
            for p in available_protons:
                if p["id"] == selected_runner:
                    proton_path = Path(p["path"])
                    break

        umu_run = find_umu_run()

        env = os.environ.copy()
        env["WINEPREFIX"] = str(prefix_path)
        if proton_path and proton_path.exists():
            env["PROTONPATH"] = str(proton_path)
        env["GAMEID"] = "umu-default"
        env.pop("LD_LIBRARY_PATH", None)

        try:
            if selected_runner == "wine" or not (umu_run and umu_run.exists()):
                cmd = ["wine", str(greed_root)]
            else:
                cmd = [str(umu_run), str(greed_root)]

            subprocess.Popen(cmd, env=env, cwd=str(spt_root))
            parent = self.parent()
            runner_name = selected_runner if selected_runner not in ("auto", "wine") else (proton_path.name if proton_path else "Proton")
            if parent and hasattr(parent, "toast"):
                parent.toast.success(f"Launching Greed.exe (SVM) [{runner_name}]...")
            elif parent and hasattr(parent, "show_toast"):
                parent.show_toast(f"Launching Greed.exe (SVM) [{runner_name}]...")
            else:
                QMessageBox.information(
                    self,
                    "Greed.exe Launched",
                    f"<b>Greed.exe</b> launched under SPT root:\n\n<code>{spt_root}</code>",
                )
        except Exception as e:
            QMessageBox.critical(self, "Error Launching Greed.exe", f"Failed to launch Greed.exe: {e}")

    def browse_spt_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select SPT Installation Folder", self.txt_spt.text())
        if dir_path:
            self.txt_spt.setText(dir_path)

    def browse_staged_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Mod Staging Stash Directory", self.txt_staged.text())
        if dir_path:
            self.txt_staged.setText(dir_path)

    def browse_server_script(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Server Script", self.txt_server.text(), "Scripts (*.sh *.exe);;All Files (*)"
        )
        if file_path:
            self.txt_server.setText(file_path)

    def browse_launcher_script(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Launcher Script", self.txt_launcher.text(), "Scripts (*.sh *.exe);;All Files (*)"
        )
        if file_path:
            self.txt_launcher.setText(file_path)

    def save_settings(self):
        spt = self.txt_spt.text().strip()
        staged = self.txt_staged.text().strip()
        server = self.txt_server.text().strip()
        launcher = self.txt_launcher.text().strip()

        if not spt or not staged or not server or not launcher:
            QMessageBox.warning(
                self,
                "Missing Required Paths",
                "<b>All path settings fields are required.</b><br><br>Please ensure no path "
                "field is left blank before saving settings.",
            )
            return

        self.cfg["spt_path"] = spt
        self.cfg["staged_dir"] = staged
        self.cfg["server_script"] = server
        self.cfg["launcher_script"] = launcher
        self.cfg["proton_runner"] = self.combo_proton.currentData()
        save_config(self.cfg)
        self.accept()


class StageInstallDialog(QDialog):
    def __init__(self, archive_path, mod_info, parent=None):
        super().__init__(parent)
        self.archive_path = Path(archive_path)
        self.mod_info = mod_info
        self.setWindowTitle(f"Stage & Install: {mod_info['title']}")
        self.resize(680, 500)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {BG}; color: {TEXT}; }}
            QLabel {{ color: {TEXT}; }}
            QTreeWidget {{ background-color: {SURFACE}; border: 1px solid {BORDER}; color: {TEXT}; border-radius: 6px; }}
            QHeaderView::section {{ background-color: {SURFACE_2}; color: {TEXT_MUTED}; font-weight: 600; padding: 6px; border: none; }}
            QPushButton {{ background-color: {SURFACE_2}; border: 1px solid {BORDER}; color: {TEXT}; padding: 6px 14px; border-radius: 6px; }}
            QPushButton:hover {{ background-color: {BORDER}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        lbl_header = QLabel(
            f"<b>Mod:</b> {{mod_info['title']}} <span style='color:{ACCENT};'>v{{mod_info.get('version', '')}}</span>"
        )
        lbl_header.setFont(QFont("Ubuntu", 14, QFont.Bold))
        layout.addWidget(lbl_header)

        deps = mod_info.get("dependencies", [])
        if deps:
            for d in deps:
                d["installed"] = is_dependency_installed(d["title"])
            missing = [d for d in deps if not d.get("installed")]
            if missing:
                dep_box = QLabel(
                    f"<b>Warning:</b> This mod requires <b>{len(missing)} missing dependency mod(s)</b>: "
                    + ", ".join(m["title"] for m in missing)
                )
                dep_box.setStyleSheet(
                    f"background-color: {BORDER}; border: 1px solid {DANGER}; border-radius: 6px; "
                    f"padding: 8px; color: {DANGER};"
                )
                layout.addWidget(dep_box)
            else:
                dep_box = QLabel(
                    f"All <b>{len(deps)} required dependency mod(s)</b> are installed and enabled in your game."
                )
                dep_box.setStyleSheet(
                    f"background-color: {SURFACE}; border: 1px solid {SUCCESS}; border-radius: 6px; "
                    f"padding: 6px; color: {SUCCESS};"
                )
                layout.addWidget(dep_box)

        size_mb = self.archive_path.stat().st_size / (1024 * 1024)
        lbl_info = QLabel(f"Downloaded Archive: <b>{self.archive_path.name}</b> ({size_mb:.2f} MB)")
        lbl_info.setStyleSheet(f"color: {TEXT_MUTED};")
        layout.addWidget(lbl_info)

        layout.addWidget(QLabel("<b>Staged Package Contents:</b>"))

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Target Destination", "Archive File / Path"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.tree)

        self.inspect_archive()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        btn_open_folder = QPushButton("Downloads Cache Folder")
        btn_open_folder.setIcon(QIcon(_nav_pixmap("folder", size=14, color=TEXT_MUTED)))
        btn_open_folder.setIconSize(QSize(14, 14))
        btn_open_folder.setProperty("role", "ghost")
        btn_open_folder.setProperty("size", "sm")
        btn_open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(DOWNLOADS_CACHE_DIR))))
        btn_layout.addWidget(btn_open_folder)
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setProperty("role", "ghost")
        btn_cancel.setProperty("size", "sm")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_install = QPushButton("Install to SPT Now")
        btn_install.setIcon(QIcon(_nav_pixmap("install", size=14, color=BG)))
        btn_install.setIconSize(QSize(14, 14))
        btn_install.setProperty("role", "primary")
        btn_install.setProperty("size", "sm")
        btn_install.clicked.connect(self.accept)
        btn_layout.addWidget(btn_install)

        layout.addLayout(btn_layout)

    def inspect_archive(self):
        self.tree.clear()
        try:
            if self.archive_path.suffix.lower() == ".zip":
                with zipfile.ZipFile(self.archive_path, "r") as z:
                    for name in sorted(z.namelist()[:150]):
                        clean_name = name.replace("\\", "/")
                        target = "SPT Root"
                        if "bepinex" in clean_name.lower():
                            target = "Client (BepInEx/plugins)"
                        elif "user/mods" in clean_name.lower() or "spt_runtime" in clean_name.lower():
                            target = "Server (user/mods)"
                        item = QTreeWidgetItem([target, clean_name])
                        self.tree.addTopLevelItem(item)
            elif self.archive_path.suffix.lower() == ".7z":
                res = subprocess.run(["7z", "l", str(self.archive_path)], capture_output=True, text=True)
                for line in res.stdout.splitlines()[:80]:
                    if "---" in line or not line.strip():
                        continue
                    item = QTreeWidgetItem(["SPT Package", line.strip()])
                    self.tree.addTopLevelItem(item)
        except Exception as e:
            item = QTreeWidgetItem(["Error", str(e)])
            self.tree.addTopLevelItem(item)


class SavePresetDialog(QDialog):
    def __init__(self, enabled_count, spt_version="SPT 4.1.3", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Preset — SPT Stash")
        self.setMinimumWidth(440)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {BG}; color: {TEXT}; }}
            QLabel {{ color: {TEXT}; font-size: 13px; }}
            QLineEdit {{ background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; color: {TEXT}; padding: 8px 12px; font-size: 13px; }}
            QLineEdit:focus {{ border-color: {ACCENT}; }}
            QPushButton {{ background-color: {SURFACE_2}; border: 1px solid {BORDER}; color: {TEXT}; padding: 8px 16px; border-radius: 6px; font-weight: 500; font-size: 13px; }}
            QPushButton:hover {{ background-color: {BORDER}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("Create New Stash Preset")
        title_lbl.setFont(QFont("Ubuntu", 14, QFont.Bold))
        layout.addWidget(title_lbl)

        sub_lbl = QLabel(f"This will snapshot your <b>{enabled_count} currently enabled mod(s)</b> ({spt_version}).")
        sub_lbl.setStyleSheet(f"color: {TEXT_MUTED}; margin-bottom: 8px;")
        layout.addWidget(sub_lbl)

        layout.addWidget(QLabel("Preset Name:"))
        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("e.g. Fika Co-Op Raid Loadout")
        layout.addWidget(self.txt_title)

        layout.addWidget(QLabel("Short Description (Optional):"))
        self.txt_desc = QLineEdit()
        self.txt_desc.setPlaceholderText("e.g. SAIN AI, UI Fixes, and Fika Server")
        layout.addWidget(self.txt_desc)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setProperty("role", "ghost")
        btn_cancel.setProperty("size", "sm")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Save Preset")
        btn_save.setIcon(QIcon(_nav_pixmap("installed", size=14, color=BG)))
        btn_save.setIconSize(QSize(14, 14))
        btn_save.setProperty("role", "primary")
        btn_save.setProperty("size", "sm")
        btn_save.clicked.connect(self.accept)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def get_data(self):
        return self.txt_title.text().strip(), self.txt_desc.text().strip()
