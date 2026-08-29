#!/usr/bin/env python3
"""SPT Stash — Local Archive Installer tab."""

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ...staging.workers import ModInstallerThread


def setup_installer_tab(self):
    layout = QVBoxLayout(self.tab_installer)

    group = QGroupBox("Install Local Mod Archive (.zip / .7z)")
    g_layout = QVBoxLayout(group)

    info_lbl = QLabel(
        "Select any SPT mod archive (.zip or .7z). The installer will automatically "
        "normalize Windows file paths, resolve folder names, and place Client (BepInEx) "
        "and Server (user/mods) components into your SPT directory."
    )
    info_lbl.setWordWrap(True)
    g_layout.addWidget(info_lbl)

    btn_select_file = QPushButton("📁 Choose Mod Archive File...")
    btn_select_file.clicked.connect(self.open_file_installer)
    g_layout.addWidget(btn_select_file)

    self.lbl_install_status = QLabel("")
    self.lbl_install_status.setStyleSheet("font-weight: bold;")
    g_layout.addWidget(self.lbl_install_status)

    layout.addWidget(group)
    layout.addStretch()


def open_file_installer(self):
    file_path, _ = QFileDialog.getOpenFileName(
        self, "Select Mod Archive", str(Path.home() / "Downloads"), "Archives (*.zip *.7z)"
    )
    if file_path:
        self.lbl_install_status.setText(f"Installing {Path(file_path).name}...")
        self.installer_thread = ModInstallerThread(file_path)
        self.installer_thread.finished.connect(self.on_mod_installed)
        self.installer_thread.start()


def on_mod_installed(self, success, message):
    if success:
        QMessageBox.information(self, "Success", message)
        self.lbl_install_status.setText("✅ " + message)
        self.load_installed_mods()
    else:
        QMessageBox.critical(self, "Error", message)
        self.lbl_install_status.setText("❌ " + message)


# ------------------ Linux Performance Tab ------------------
