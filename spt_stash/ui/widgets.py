#!/usr/bin/env python3
"""SPT Stash — small reusable UI widgets."""

import urllib.request
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QTextDocument
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QStyle, QStyledItemDelegate, QTextBrowser

from ..catalog.dependencies import check_dep_status
from ..paths import IMAGE_CACHE_DIR


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
    """Custom list-item painter for the mod catalog."""

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 58)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        rect = option.rect.adjusted(4, 2, -4, -2)
        mod = index.data(Qt.UserRole)
        is_selected = bool(option.state & QStyle.State_Selected)
        is_hovered = bool(option.state & QStyle.State_MouseOver)

        if not mod:
            painter.restore()
            return

        status, _ = check_dep_status(mod.get("title", ""))

        if status == "ENABLED":
            bg_color = QColor("#1e3a29") if not is_selected else QColor("#2b4c37")
            border_color = QColor("#a6e3a1")
        elif status == "STAGED_DISABLED":
            bg_color = QColor("#3a2c1e") if not is_selected else QColor("#4c3a27")
            border_color = QColor("#fab387")
        elif is_selected:
            bg_color = QColor("#313244")
            border_color = QColor("#89b4fa")
        elif is_hovered:
            bg_color = QColor("#262637")
            border_color = QColor("#45475a")
        else:
            bg_color = QColor("#181825")
            border_color = QColor("#262637")

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1.5 if (is_selected or status != "MISSING") else 1.0))
        painter.drawRoundedRect(rect, 8, 8)

        font_title = QFont("Ubuntu", 11, QFont.Bold)
        painter.setFont(font_title)
        painter.setPen(
            QPen(
                QColor("#a6e3a1")
                if status == "ENABLED"
                else (
                    QColor("#fab387")
                    if status == "STAGED_DISABLED"
                    else (QColor("#89b4fa") if is_selected else QColor("#cdd6f4"))
                )
            )
        )

        title = mod.get("title", "Unknown")
        title_rect = rect.adjusted(12, 6, -140, -26)
        metrics = painter.fontMetrics()
        elided_title = metrics.elidedText(title, Qt.ElideRight, max(50, title_rect.width()))
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_title)

        font_sub = QFont("Ubuntu", 9)
        painter.setFont(font_sub)
        painter.setPen(QPen(QColor("#bac2de") if is_selected else QColor("#a6adc8")))

        author = mod.get("creator", "Community")
        ver = mod.get("version", "")
        spt_ver = mod.get("spt_version", "")
        f_stat = mod.get("fika_status", "")

        sub_text = f"by {author}"
        if ver:
            sub_text += f"  •  v{ver}"
        if spt_ver:
            sub_text += f"  •  {spt_ver}"
        if "Compatible" in f_stat or f_stat == "Yes":
            sub_text += "  •  🟢 Fika"
        if status == "ENABLED":
            sub_text += "  •  ✅ Installed"
        elif status == "STAGED_DISABLED":
            sub_text += "  •  ⚠️ Stashed (Disabled)"

        sub_rect = rect.adjusted(12, 28, -140, -6)
        elided_sub = metrics.elidedText(sub_text, Qt.ElideRight, max(50, sub_rect.width()))
        painter.drawText(sub_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_sub)

        dl_cnt = mod.get("downloads", 0)
        end_cnt = mod.get("endorsements", 0)
        stats_str = ""
        if dl_cnt:
            stats_str += f"📥 {dl_cnt:,} "
        if end_cnt:
            stats_str += f"👍 {end_cnt}"

        if stats_str:
            painter.setFont(QFont("Ubuntu", 9, QFont.Bold))
            painter.setPen(QPen(QColor("#a6e3a1") if is_selected else QColor("#fab387")))
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
