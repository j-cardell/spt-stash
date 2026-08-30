#!/usr/bin/env python3
"""SPT Stash — small reusable UI widgets."""

import urllib.request
from pathlib import Path

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QTextDocument
from PySide6.QtWidgets import (
    QAbstractButton,
    QGraphicsOpacityEffect,
    QLabel,
    QLineEdit,
    QStyle,
    QStyledItemDelegate,
    QTextBrowser,
    QWidget,
)

from ..catalog.dependencies import check_dep_status
from ..paths import IMAGE_CACHE_DIR


class ToggleSwitch(QAbstractButton):
    """Modern iOS/HTML-style animated toggle switch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(False)
        self.setFixedSize(36, 20)
        self.setCursor(Qt.PointingHandCursor)
        self._offset = 3.0

        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.toggled.connect(self._on_toggled)

    def _get_offset(self):
        return self._offset

    def _set_offset(self, val):
        self._offset = val
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def _on_toggled(self, checked):
        target = 18.5 if checked else 3.0
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(target)
        self._anim.start()

    def setChecked(self, checked):
        super().setChecked(checked)
        self._offset = 18.5 if checked else 3.0
        self.update()

    def sizeHint(self):
        return QSize(36, 20)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = 34.0
        h = 19.0
        x = 1.0
        y = 0.5
        radius = h / 2.0

        if self.isChecked():
            track_bg = QColor(74, 222, 128, 40)
            track_border = QColor(74, 222, 128, 100)
            knob_color = QColor("#4ade80")
        else:
            track_bg = QColor("#1e222d")
            track_border = QColor("#3a4052")
            knob_color = QColor("#7f8698")

        painter.setBrush(QBrush(track_bg))
        painter.setPen(QPen(track_border, 1.0))
        painter.drawRoundedRect(QRectF(x, y, w, h), radius, radius)

        knob_d = 13.0
        knob_y = y + (h - knob_d) / 2.0
        painter.setBrush(QBrush(knob_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(self._offset, knob_y, knob_d, knob_d))
        painter.end()


class SearchField(QWidget):
    """QLineEdit with a left-aligned search icon, matching V4 toolbar style."""

    textChanged = Signal(str)

    def __init__(self, parent=None, width=320, placeholder="Search mods..."):
        super().__init__(parent)
        self.setFixedWidth(width)
        self.setFixedHeight(32)

        self.line_edit = QLineEdit(self)
        self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.textChanged.connect(self.textChanged.emit)
        self.line_edit.setGeometry(0, 0, width, 32)
        # Pad left so typed text doesn't overlap the icon
        self.line_edit.setStyleSheet("padding-left: 30px;")

        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(_search_pixmap())
        icon_lbl.setStyleSheet("background: transparent;")
        icon_lbl.setFixedSize(14, 14)
        icon_lbl.move(10, (32 - 14) // 2)

    def text(self):
        return self.line_edit.text()


def _search_pixmap():
    """Render a small magnifying-glass icon as QPixmap."""
    size = 14
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#7f8698"), 1.8))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QRectF(1.5, 1.5, 8, 8))
    painter.drawLine(int(size - 4), int(size - 4), size - 1, size - 1)
    painter.end()
    return pix


class CheckBox(QWidget):
    """Custom painted checkbox matching V4 tokens (rounded square + accent fill)."""

    toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self.setFixedSize(18, 18)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Select row")

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        if self._checked != bool(checked):
            self._checked = bool(checked)
            self.update()
            self.toggled.emit(self._checked)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setChecked(not self._checked)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)

        if self._checked:
            painter.setBrush(QBrush(QColor("#7c8cff")))
            painter.setPen(QPen(QColor("#7c8cff"), 1))
        else:
            painter.setBrush(QBrush(QColor("#14161d")))
            painter.setPen(QPen(QColor("#3a4052"), 1))

        painter.drawRoundedRect(rect, 4, 4)

        if self._checked:
            painter.setPen(QPen(QColor("#0f1016"), 2))
            painter.setBrush(Qt.NoBrush)
            x = rect.x() + 4
            y = rect.y() + 7
            w = rect.width() - 8
            h = rect.height() - 8
            path = QPainterPath()
            path.moveTo(x, y + h * 0.35)
            path.lineTo(x + w * 0.4, y + h)
            path.lineTo(x + w, y)
            painter.drawPath(path)


class RemoteImageTextBrowser(QTextBrowser):
    """QTextBrowser that caches remote <img> resources to disk + memory."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self._memory_cache = {}

    def loadResource(self, type_id, name):
        if type_id == QTextDocument.ResourceType.ImageResource:
            url_str = name.toString() if hasattr(name, "toString") else str(name)
            if url_str in self._memory_cache:
                return self._memory_cache[url_str]

            if url_str.startswith(("http://", "https://")):
                img_name = Path(url_str).name
                local_path = IMAGE_CACHE_DIR / img_name

                if local_path.exists():
                    img = QImage(str(local_path))
                    if not img.isNull():
                        self._memory_cache[url_str] = img
                        return img

                try:
                    req = urllib.request.Request(url_str, headers={"User-Agent": "Mozilla/5.0"})
                    data = urllib.request.urlopen(req, timeout=5).read()
                    img = QImage()
                    if img.loadFromData(data):
                        img.save(str(local_path))
                        self._memory_cache[url_str] = img
                        return img
                except Exception:
                    pass
        return super().loadResource(type_id, name)


class ModItemDelegate(QStyledItemDelegate):
    """Custom list-item painter for the mod catalog (V4 tokens)."""

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 64)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        rect = option.rect.adjusted(4, 3, -4, -3)
        mod = index.data(Qt.UserRole)
        is_selected = bool(option.state & QStyle.State_Selected)
        is_hovered = bool(option.state & QStyle.State_MouseOver)

        if not mod:
            painter.restore()
            return

        status, _ = check_dep_status(mod.get("title", ""))

        # V4 palette
        BG = "#14161d"
        SURFACE = "#1a1d27"
        SURFACE_HOVER = "#212531"
        BORDER = "#232733"
        BORDER_HOVER = "#2e3346"
        ACCENT = "#7c8cff"
        TEXT = "#eceef3"
        TEXT_MUTED = "#7f8698"
        SUCCESS = "#4ade80"
        WARNING = "#fbbf24"

        if status == "ENABLED":
            border_color = QColor(SUCCESS)
        elif status == "STAGED_DISABLED":
            border_color = QColor(WARNING)
        elif is_selected:
            border_color = QColor(ACCENT)
        elif is_hovered:
            border_color = QColor(BORDER_HOVER)
        else:
            border_color = QColor(BORDER)

        if is_selected:
            bg_color = QColor(SURFACE)
        elif is_hovered:
            bg_color = QColor(SURFACE_HOVER)
        else:
            bg_color = QColor(BG)

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1.0))
        painter.drawRoundedRect(rect, 8, 8)

        font_title = QFont("Ubuntu", 11, QFont.Bold)
        painter.setFont(font_title)
        painter.setPen(QPen(QColor(TEXT)))

        title = mod.get("title", "Unknown")
        title_rect = rect.adjusted(12, 8, -150, -28)
        metrics = painter.fontMetrics()
        elided_title = metrics.elidedText(title, Qt.ElideRight, max(50, title_rect.width()))
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_title)

        font_sub = QFont("Ubuntu", 9)
        painter.setFont(font_sub)
        painter.setPen(QPen(QColor(TEXT_MUTED)))

        author = mod.get("creator", "Community")
        ver = mod.get("version", "")
        spt_ver = mod.get("spt_version", "")

        sub_text = f"by {author}"
        if ver:
            sub_text += f"  •  v{ver}"
        if spt_ver:
            sub_text += f"  •  {spt_ver}"

        sub_rect = rect.adjusted(12, 30, -150, -6)
        elided_sub = metrics.elidedText(sub_text, Qt.ElideRight, max(50, sub_rect.width()))
        painter.drawText(sub_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_sub)

        dl_cnt = mod.get("downloads", 0)
        end_cnt = mod.get("endorsements", 0)
        stats_str = ""
        if dl_cnt:
            stats_str += f"⬇ {dl_cnt:,} "
        if end_cnt:
            stats_str += f"★ {end_cnt}"

        if stats_str:
            painter.setFont(QFont("Ubuntu", 9, QFont.Bold))
            painter.setPen(QPen(QColor(TEXT_MUTED)))
            painter.drawText(rect.adjusted(-12, 0, -12, 0), Qt.AlignRight | Qt.AlignVCenter, stats_str.strip())

        painter.restore()


class ToastNotification(QLabel):
    """Floating pill notification with smooth fade-in and fade-out animations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)
        self.hide()

        self._fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self._fade_anim.setDuration(220)
        self._fade_anim.setEasingCurve(QEasingCurve.InOutQuad)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

    def show_message(
        self,
        text,
        duration_ms=2200,
        bg_color="#181825",
        border_color="#89b4fa",
        text_color="#cdd6f4",
    ):
        self.setText(text)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                border: 2px solid {border_color};
                border-radius: 10px;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: bold;
            }}
        """)
        self.adjustSize()

        if self.parent():
            p_rect = self.parent().rect()
            x = (p_rect.width() - self.width()) // 2
            y = p_rect.height() - self.height() - 36
            self.move(max(10, x), max(10, y))

        self.show()
        self.raise_()

        self._fade_anim.stop()
        self._fade_anim.setStartValue(self.opacity_effect.opacity())
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

        self._hide_timer.start(duration_ms)

    def _fade_out(self):
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self.opacity_effect.opacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self._on_fade_out_finished)
        self._fade_anim.start()

    def _on_fade_out_finished(self):
        try:
            self._fade_anim.finished.disconnect(self._on_fade_out_finished)
        except Exception:
            pass
        if self.opacity_effect.opacity() <= 0.01:
            self.hide()
