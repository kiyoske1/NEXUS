"""Lightweight custom-painted activity chart for the NEXUS dashboard."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class WeeklyActivityChart(QWidget):
    """A dependency-free seven-day activity chart with focus bars and quest markers."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._days: list[dict] = []
        self.setMinimumHeight(154)
        self.setMaximumHeight(190)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_data(self, days: list[dict]) -> None:
        self._days = list(days)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(QFont("Segoe UI", 9))
        bounds = self.rect().adjusted(8, 8, -8, -6)
        if not self._days:
            painter.setPen(QColor("#858797"))
            painter.drawText(bounds, Qt.AlignmentFlag.AlignCenter, "Your activity will appear here.")
            return

        left, right = bounds.left() + 8, bounds.right() - 6
        top, baseline = bounds.top() + 8, bounds.bottom() - 25
        chart_height = max(35.0, baseline - top)
        chart_width = max(10.0, right - left)
        count = len(self._days)
        slot = chart_width / count
        max_focus = max((int(day.get("focus", 0)) for day in self._days), default=0)
        max_focus = max(25, max_focus)

        painter.setPen(QPen(QColor("#292a36"), 1, Qt.PenStyle.DashLine))
        for fraction in (0.25, 0.5, 0.75, 1.0):
            y = baseline - chart_height * fraction
            painter.drawLine(int(left), int(y), int(right), int(y))

        path = QPainterPath()
        has_points = False
        for index, day in enumerate(self._days):
            center_x = left + slot * (index + 0.5)
            minutes = max(0, int(day.get("focus", 0)))
            quests = max(0, int(day.get("quests", 0)))
            bar_height = chart_height * minutes / max_focus
            bar_width = min(24.0, slot * 0.48)
            bar = QRectF(center_x - bar_width / 2, baseline - bar_height, bar_width, max(3.0, bar_height))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#292a37"))
            painter.drawRoundedRect(QRectF(center_x - bar_width / 2, top, bar_width, chart_height), 5, 5)
            painter.setBrush(QColor("#c7f36b") if minutes else QColor("#454154"))
            painter.drawRoundedRect(bar, 5, 5)

            point_y = baseline - min(chart_height * 0.9, quests * 9 + 5)
            if not has_points:
                path.moveTo(center_x, point_y)
                has_points = True
            else:
                path.lineTo(center_x, point_y)
            painter.setPen(QPen(QColor("#aaa1d7"), 1.5))
            painter.setBrush(QColor("#171722"))
            painter.drawEllipse(QRectF(center_x - 3.2, point_y - 3.2, 6.4, 6.4))

            painter.setPen(QColor("#858797"))
            painter.drawText(QRectF(center_x - slot / 2, baseline + 8, slot, 18),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                             str(day.get("label", "")))

        if has_points:
            painter.setPen(QPen(QColor("#aaa1d7"), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        painter.setPen(QColor("#858797"))
        painter.drawText(QRectF(left, top - 2, chart_width, 14),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         "FOCUS MINUTES  /  QUESTS COMPLETED")
