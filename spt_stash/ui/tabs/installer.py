#!/usr/bin/env python3
"""SPT Stash — Local Archive Installer tab."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ...staging.workers import ModInstallerThread
from ..theme import ACCENT, BORDER, BORDER_HOVER, SURFACE, SURFACE_2, TEXT, TEXT_MUTED


def setup_installer_tab(self):
    layout = QVBoxLayout(self.tab_installer)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(14)

    lbl_title = QLabel("Install Mod Archive")
    lbl_title.setStyleSheet("font-size: 18px; font-weight: 700; letter-spacing: -0.02em;")
    layout.addWidget(lbl_title)

    lbl_subtitle = QLabel("Drop a .zip or .7z from sp-mod.com or your own collection")
    lbl_subtitle.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; margin-bottom: 4px;")
    layout.addWidget(lbl_subtitle)

    # Single dashed drop zone
    self.dropzone = QFrame()
    self.dropzone.setObjectName("dropZone")
    self.dropzone.setAcceptDrops(True)
    self.dropzone.setStyleSheet(f"""
        QFrame#dropZone {{
            background-color: {SURFACE};
            border: 2px dashed {BORDER_HOVER};
            border-radius: 12px;
            padding: 40px 24px;
        }}
        QFrame#dropZone:hover {{
            border-color: {ACCENT};
            background-color: {SURFACE_2};
        }}
    """)
    dz_layout = QVBoxLayout(self.dropzone)
    dz_layout.setAlignment(Qt.AlignCenter)
    dz_layout.setSpacing(8)
    dz_layout.setContentsMargins(24, 24, 24, 24)

    dz_title = QLabel("Drop a mod archive here")
    dz_title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {TEXT}; background: transparent; border: none;")
    dz_title.setAlignment(Qt.AlignCenter)
    dz_layout.addWidget(dz_title)

    dz_sub = QLabel(".zip / .7z / folders are auto-detected as Client, Server, or Dual mods")
    dz_sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent; border: none;")
    dz_sub.setAlignment(Qt.AlignCenter)
    dz_layout.addWidget(dz_sub)

    layout.addWidget(self.dropzone)

    # Staged file card (hidden until file chosen)
    self.install_file_card = QFrame()
    self.install_file_card.setStyleSheet(f"""
        QFrame {{
            background-color: {SURFACE};
            border: 1px solid {BORDER};
            border-radius: 10px;
            padding: 12px 16px;
        }}
    """)
    card_layout = QHBoxLayout(self.install_file_card)
    card_layout.setContentsMargins(12, 8, 12, 8)
    card_layout.setSpacing(12)

    self.lbl_install_file = QLabel("No archive selected")
    self.lbl_install_file.setStyleSheet(f"color: {TEXT}; font-size: 13px;")
    card_layout.addWidget(self.lbl_install_file)
    card_layout.addStretch()

    self.lbl_install_type = QLabel("")
    self.lbl_install_type.setStyleSheet(f"color: {ACCENT}; font-size: 12px;")
    card_layout.addWidget(self.lbl_install_type)

    self.btn_install_archive = QPushButton("Install")
    self.btn_install_archive.setProperty("role", "success")
    self.btn_install_archive.setProperty("size", "sm")
    self.btn_install_archive.setEnabled(False)
    self.btn_install_archive.clicked.connect(self.start_local_install)
    card_layout.addWidget(self.btn_install_archive)

    self.btn_remove_archive = QPushButton("Remove")
    self.btn_remove_archive.setProperty("role", "ghost")
    self.btn_remove_archive.setProperty("size", "sm")
    self.btn_remove_archive.setEnabled(False)
    self.btn_remove_archive.clicked.connect(self.clear_local_install)
    card_layout.addWidget(self.btn_remove_archive)

    self.install_file_card.setVisible(False)
    layout.addWidget(self.install_file_card)

    # Info cards grid
    info_grid = QHBoxLayout()
    info_grid.setSpacing(12)

    def _info_card(title, body):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
            QLabel {{
                background: transparent;
                border: none;
                color: {TEXT};
            }}
        """)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 14, 16, 14)
        c_layout.setSpacing(8)
        tl = QLabel(title)
        tl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;")
        c_layout.addWidget(tl)
        bl = QLabel(body)
        bl.setStyleSheet(f"color: {TEXT}; font-size: 12px; line-height: 1.4;")
        bl.setWordWrap(True)
        c_layout.addWidget(bl)
        return card

    info_grid.addWidget(_info_card(
        "CLIENT MODS",
        "Detected by BepInEx plugins folder. Staged to .staged/client/"
    ))
    info_grid.addWidget(_info_card(
        "SERVER MODS",
        "Detected by user/mods folder. Staged to .staged/server/"
    ))
    info_grid.addWidget(_info_card(
        "DEPENDENCIES",
        "Missing dependencies are auto-fetched from the Forge catalog after install."
    ))
    layout.addLayout(info_grid)

    layout.addStretch()

    # Drag/drop handlers
    self.dropzone.dragEnterEvent = lambda e: e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()
    self.dropzone.dropEvent = self._on_install_drop


def _on_install_drop(self, event):
    urls = event.mimeData().urls()
    if urls:
        self.set_install_archive(Path(urls[0].toLocalFile()))


def set_install_archive(self, path: Path):
    if not path or not path.exists():
        return
    suffix = path.suffix.lower()
    if suffix not in (".zip", ".7z"):
        QMessageBox.warning(self, "Unsupported File", "Only .zip or .7z archives are supported.")
        return
    self.pending_archive_path = path
    self.lbl_install_file.setText(path.name)
    size_mb = path.stat().st_size / (1024 * 1024)
    self.lbl_install_type.setText(f"{size_mb:.1f} MB")
    self.btn_install_archive.setEnabled(True)
    self.btn_remove_archive.setEnabled(True)
    self.install_file_card.setVisible(True)


def clear_local_install(self):
    self.pending_archive_path = None
    self.lbl_install_file.setText("No archive selected")
    self.lbl_install_type.setText("")
    self.btn_install_archive.setEnabled(False)
    self.btn_remove_archive.setEnabled(False)
    self.install_file_card.setVisible(False)


def start_local_install(self):
    path = getattr(self, "pending_archive_path", None)
    if not path:
        return
    self.btn_install_archive.setEnabled(False)
    self.btn_install_archive.setText("Installing...")
    self.show_download_progress(f"Installing {path.name}...")
    self.installer_thread = ModInstallerThread(path)
    self.installer_thread.finished.connect(self.on_mod_installed)
    self.installer_thread.start()


def open_file_installer(self):
    file_path, _ = QFileDialog.getOpenFileName(
        self, "Select Mod Archive", str(Path.home() / "Downloads"), "Archives (*.zip *.7z)"
    )
    if file_path:
        self.set_install_archive(Path(file_path))


def on_mod_installed(self, success, message):
    self.hide_download_progress()
    self.btn_install_archive.setText("Install")
    self.btn_install_archive.setEnabled(True)
    if success:
        QMessageBox.information(self, "Success", message)
        self.clear_local_install()
        self.load_installed_mods()
    else:
        QMessageBox.critical(self, "Error", message)


# ------------------ Linux Performance Tab ------------------
