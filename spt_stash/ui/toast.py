#!/usr/bin/env python3
"""Animated overlay toast notifications for SPT Stash."""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QLabel, QVBoxLayout

from .theme import ACCENT, DANGER, RADIUS, SUCCESS, SURFACE_2, TEXT


class ToastManager:
    """Non-blocking animated pill toasts positioned at top-right of main window."""

    def __init__(self, parent):
        self.parent = parent
        self.toasts = []

    def _show(self, message: str, color: str = SUCCESS, duration: int = 2200):
        toast = QFrame(self.parent)
        toast.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        toast.setStyleSheet(f"""
            QFrame {{
                background-color: {SURFACE_2};
                border: 1px solid {color};
                border-radius: {RADIUS}px;
                padding: 6px 12px;
            }}
            QLabel {{
                color: {TEXT};
                font-size: 12px;
                font-weight: 600;
                background: transparent;
            }}
        """)
        layout = QVBoxLayout(toast)
        layout.setContentsMargins(10, 6, 10, 6)
        lbl = QLabel(message)
        layout.addWidget(lbl)
        toast.adjustSize()

        self.toasts.append(toast)
        self._reposition_toasts()
        toast.show()

        effect = QGraphicsOpacityEffect(toast)
        toast.setGraphicsEffect(effect)

        anim_in = QPropertyAnimation(effect, b"opacity", toast)
        anim_in.setDuration(140)
        anim_in.setStartValue(0.0)
        anim_in.setEndValue(1.0)
        anim_in.setEasingCurve(QEasingCurve.OutQuad)
        toast._anim_in = anim_in
        anim_in.start()

        # Timer to start fade out
        timer = QTimer(toast)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda t=toast, e=effect: self._fade_out(t, e))
        toast._timer = timer
        timer.start(duration)

    def _fade_out(self, toast: QFrame, effect: QGraphicsOpacityEffect):
        if not toast or not toast.isVisible():
            self._remove(toast)
            return

        anim_out = QPropertyAnimation(effect, b"opacity", toast)
        anim_out.setDuration(160)
        anim_out.setStartValue(1.0)
        anim_out.setEndValue(0.0)
        anim_out.setEasingCurve(QEasingCurve.InQuad)
        anim_out.finished.connect(lambda t=toast: self._remove(t))
        toast._anim_out = anim_out
        anim_out.start()

    def _remove(self, toast: QFrame):
        if toast in self.toasts:
            self.toasts.remove(toast)
        toast.hide()
        toast.deleteLater()
        self._reposition_toasts()

    def _reposition_toasts(self):
        curr_y = 20
        p_w = self.parent.width() if self.parent else 1180
        for t in self.toasts:
            x = max(10, p_w - t.width() - 24)
            t.move(x, curr_y)
            curr_y += t.height() + 8

    def success(self, msg: str):
        self._show(msg, SUCCESS)

    def error(self, msg: str):
        self._show(msg, DANGER)

    def info(self, msg: str):
        self._show(msg, ACCENT)
