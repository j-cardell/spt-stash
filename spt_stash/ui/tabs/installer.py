#!/usr/bin/env python3
"""SPT Stash — Local Archive Installer tab."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ...staging.workers import ModInstallerThread


def setup_installer_tab(self):
    layout = QVBoxLayout(self.tab_installer)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(14)

    lbl_title = QLabel("Install Local Mod Archive")
    lbl_title.setStyleSheet("font-size: 18px; font-weight: 700; letter-spacing: -0.02em;")
    layout.addWidget(lbl_title)

    dropzone = QFrame()
    dropzone.setStyleSheet("""
        QFrame {
            background-color: #14161d;
            border: 2px dashed #2e3346;
            border-radius: 12px;
            padding: 40px 24px;
        }
        QFrame:hover {
            border-color: #7c8cff;
            background-color: #1a1d27;
        }
    """)
    d_layout = QVBoxLayout(dropzone)
    d_layout.setAlignment(Qt.AlignCenter)
    d_layout.setSpacing(12)

    icon_lbl = QLabel("📦")
    icon_lbl.setStyleSheet("font-size: 42px; background: transparent;")
    icon_lbl.setAlignment(Qt.AlignCenter)
    d_layout.addWidget(icon_lbl)

    title_lbl = QLabel("Select a Mod Archive (.zip or .7z)")
    title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #eceef3; background: transparent;")
    title_lbl.setAlignment(Qt.AlignCenter)
    d_layout.addWidget(title_lbl)

    info_lbl = QLabel(
        "SPT Stash automatically normalizes Windows folder structures, extracts root DLLs and executables,\n"
        "and places Client (BepInEx/plugins) and Server (user/mods) components into your Stash."
    )
    info_lbl.setStyleSheet("color: #7f8698; font-size: 12.5px; line-height: 1.4; background: transparent;")
    info_lbl.setAlignment(Qt.AlignCenter)
    info_lbl.setWordWrap(True)
    d_layout.addWidget(info_lbl)

    btn_select_file = QPushButton("📁 Choose File...")
    btn_select_file.setProperty("role", "primary")
    btn_select_file.setProperty("size", "lg")
    btn_select_file.setFixedWidth(200)
    btn_select_file.clicked.connect(self.open_file_installer)
    d_layout.addWidget(btn_select_file, alignment=Qt.AlignCenter)

    layout.addWidget(dropzone)

    self.lbl_install_status = QLabel("")
    self.lbl_install_status.setStyleSheet("font-size: 13px; font-weight: 600; color: #4ade80;")
    self.lbl_install_status.setAlignment(Qt.AlignCenter)
    layout.addWidget(self.lbl_install_status)
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
