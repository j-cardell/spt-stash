#!/usr/bin/env python3
"""SPT Stash — full QSS stylesheet generated from theme tokens."""

from .theme import (
    ACCENT,
    ACCENT_DIM,
    BG,
    BORDER,
    BORDER_HOVER,
    DANGER,
    DANGER_DIM,
    FONT_MAIN,
    RADIUS,
    SIDEBAR_W,
    SUCCESS,
    SURFACE,
    SURFACE_2,
    SURFACE_3,
    TEXT,
    TEXT_MUTED,
    WARNING,
)


def get_app_stylesheet() -> str:
    return f"""
/* ── Base ─────────────────────────────────────────────────────────────── */
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: {FONT_MAIN};
    font-size: 13px;
}}

/* ── Sidebar ───────────────────────────────────────────────────────────── */
QFrame#sidebar {{
    background-color: {SURFACE};
    border-right: 1px solid {BORDER};
    min-width: {SIDEBAR_W}px;
    max-width: {SIDEBAR_W}px;
}}
QLabel#brandName {{
    font-weight: 700;
    font-size: 15px;
    color: {TEXT};
    letter-spacing: -0.01em;
}}

/* ── Navigation buttons ─────────────────────────────────────────────────── */
QPushButton[nav="true"] {{
    background: transparent;
    color: {TEXT_MUTED};
    border: none;
    border-radius: 7px;
    padding: 9px 12px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
    margin-bottom: 2px;
}}
QPushButton[nav="true"]:hover {{
    background: rgba(255, 255, 255, 0.04);
    color: {TEXT};
}}
QPushButton[nav="true"]:checked {{
    background: {SURFACE_2};
    color: {ACCENT};
    font-weight: 600;
}}

/* ── Buttons ────────────────────────────────────────────────────────────── */
QPushButton {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    color: {TEXT};
    padding: 7px 12px;
    border-radius: {RADIUS}px;
    font-weight: 600;
    font-size: 12px;
}}
QPushButton:hover {{ background: {SURFACE_3}; border-color: {BORDER_HOVER}; }}

QPushButton[role="primary"] {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: {BG};
    font-weight: 700;
}}
QPushButton[role="primary"]:hover {{ background: #929fff; border-color: #929fff; }}

QPushButton[role="success"] {{
    background: rgba(74, 222, 128, 0.08);
    border-color: rgba(74, 222, 128, 0.18);
    color: {SUCCESS};
}}
QPushButton[role="success"]:hover {{ background: rgba(74, 222, 128, 0.14); }}

QPushButton[role="danger"] {{
    background: {DANGER_DIM};
    border-color: rgba(248, 113, 113, 0.22);
    color: {DANGER};
}}
QPushButton[role="danger"]:hover {{ background: rgba(248, 113, 113, 0.16); }}

QPushButton[role="ghost"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {TEXT_MUTED};
}}
QPushButton[role="ghost"]:hover {{
    background: {SURFACE_2};
    border-color: {BORDER};
    color: {TEXT};
}}

QPushButton[size="sm"] {{ padding: 5px 10px; font-size: 11.5px; }}
QPushButton[size="lg"] {{ padding: 9px 16px; font-size: 13px; font-weight: 700; }}

/* ── Inputs / search ────────────────────────────────────────────────────── */
QLineEdit, QComboBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 7px 12px;
    color: {TEXT};
    font-size: 12.5px;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    color: {TEXT};
    selection-background-color: {SURFACE_2};
    selection-color: {ACCENT};
}}

/* ── Filter chips ───────────────────────────────────────────────────────── */
QPushButton[chip="true"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 6px 12px;
    color: {TEXT_MUTED};
    font-size: 12px;
    font-weight: 600;
}}
QPushButton[chip="true"]:hover {{ color: {TEXT}; border-color: {BORDER_HOVER}; }}
QPushButton[chip="true"]:checked {{
    background: {ACCENT_DIM};
    border-color: rgba(124, 140, 255, 0.3);
    color: {ACCENT};
}}

/* ── Server status dot ─────────────────────────────────────────────────── */
QFrame#serverPanel {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
    padding: 12px 10px;
}}
QLabel#serverStatus {{ color: {TEXT_MUTED}; font-size: 11.5px; }}

/* ── Installed Mods table ──────────────────────────────────────────────── */
QTableWidget#tableMods {{
    background: {BG};
    border: none;
    gridline-color: transparent;
    border-top: 1px solid {BORDER};
}}
QTableWidget#tableMods::item {{ padding: 8px 6px; border-bottom: 1px solid {BORDER}; }}
QTableWidget#tableMods::item:selected {{
    background-color: rgba(124, 140, 255, 0.10);
    color: {TEXT};
}}
QTableWidget#tableMods::item:hover {{
    background-color: rgba(255, 255, 255, 0.03);
}}
QHeaderView::section {{
    background: {BG};
    color: {TEXT_MUTED};
    font-size: 10.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 10px 8px;
}}

/* ── Author link (clickable label) ─────────────────────────────────────── */
QLabel[role="authorLink"] {{
    color: {ACCENT};
    font-size: 11.5px;
    text-decoration: none;
}}
QLabel[role="authorLink"]:hover {{ text-decoration: underline; }}

/* ── Checkboxes (Row Multi-Selection) ─────────────────────────────────── */
QCheckBox {{
    spacing: 0;
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 4px;
    background-color: {SURFACE};
    border: 1px solid {BORDER_HOVER};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

/* ── Action icon buttons in table rows ─────────────────────────────────── */
QPushButton[iconBtn="true"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {TEXT_MUTED};
    padding: 3px;
    border-radius: 5px;
    font-size: 13px;
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
}}
QPushButton[iconBtn="true"]:hover {{
    background: {SURFACE_2};
    border-color: {BORDER};
    color: {TEXT};
}}
QPushButton[iconBtn="true"][danger="true"]:hover {{
    background: {DANGER_DIM};
    border-color: rgba(248, 113, 113, 0.3);
    color: {DANGER};
}}

/* ── Pills (Status badges) ─────────────────────────────────────────────── */
QLabel[pill="true"] {{
    font-size: 11px;
    font-weight: 600;
    padding: 2px 9px;
    border-radius: 10px;
    min-height: 18px;
    max-height: 18px;
}}
QLabel[pill="success"] {{
    background-color: rgba(74, 222, 128, 0.12);
    color: {SUCCESS};
    border: 1px solid rgba(74, 222, 128, 0.25);
}}
QLabel[pill="muted"] {{
    background-color: rgba(127, 134, 152, 0.14);
    color: {TEXT_MUTED};
    border: 1px solid rgba(127, 134, 152, 0.28);
}}
QLabel[pill="warn"] {{
    background-color: rgba(251, 191, 36, 0.10);
    color: {WARNING};
    border: 1px solid rgba(251, 191, 36, 0.25);
}}
QLabel[pill="accent"] {{
    background-color: {ACCENT_DIM};
    color: {ACCENT};
    border: 1px solid rgba(124, 140, 255, 0.3);
}}

/* ── Performance group boxes & Hardware Banner ─────────────────────────── */
QGroupBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
    margin-top: 14px;
    padding: 14px 16px;
    font-weight: 650;
    font-size: 13px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: {TEXT};
}}

QFrame#hwBanner {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 14px 16px;
}}

/* ── Text browsers ─────────────────────────────────────────────────────── */
QTextBrowser {{
    background: {BG};
    border: none;
    color: {TEXT};
    font-size: 12.5px;
}}

/* ── Bulk / status bar ─────────────────────────────────────────────────── */
QFrame#bulkBar {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
}}
QLabel#bulkCount {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}

/* ── Scrollbars ─────────────────────────────────────────────────────────── */
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""
