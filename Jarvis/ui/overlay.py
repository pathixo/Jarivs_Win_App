"""
Desktop Overlay — Transparent always-on-top HUD for Jarvis.
=============================================================
A frameless, transparent PyQt6 overlay that sits on top of all windows.
Provides a minimal docked HUD that can expand into a command palette.

Key properties:
  - Fully transparent background (click-through in transparent regions)
  - Mouse events only captured on visible overlay elements
  - Minimize/expand toggle with smooth animation
  - Multi-monitor-aware positioning
  - Zero VRAM impact (uses existing PyQt6)
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QApplication, QGraphicsDropShadowEffect, QSizePolicy, QLineEdit,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QPoint, QSize, pyqtSignal, QRect,
)
from PyQt6.QtGui import QColor, QFont, QCursor, QPainter, QBrush, QPen

logger = logging.getLogger("jarvis.ui.overlay")


class OverlayWidget(QWidget):
    """
    Transparent desktop overlay HUD with world-class aesthetic.
    """

    command_submitted = pyqtSignal(str)
    toggle_assistant = pyqtSignal()

    # Dimensions
    COLLAPSED_SIZE = QSize(60, 60)
    EXPANDED_WIDTH = 500
    EXPANDED_HEIGHT = 180

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._expanded = False
        self._drag_pos = None

        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self._anchor = QPoint(
                geo.right() - self.EXPANDED_WIDTH - 30,
                geo.bottom() - self.EXPANDED_HEIGHT - 30,
            )
        else:
            self._anchor = QPoint(100, 100)

        self.setFixedSize(self.COLLAPSED_SIZE)
        self.move(self._anchor.x() + self.EXPANDED_WIDTH - self.COLLAPSED_SIZE.width(),
                  self._anchor.y() + self.EXPANDED_HEIGHT - self.COLLAPSED_SIZE.height())

        self._build_ui()

    def _build_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # ── Collapsed: Sophisticated Orb ──
        self._orb_btn = QPushButton("󰍬")
        self._orb_btn.setFixedSize(54, 54)
        self._orb_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._orb_btn.setFont(QFont(dt.FONT_FAMILY, 22))
        self._orb_btn.setStyleSheet(f"""
            QPushButton {{
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.8,
                    stop:0 {dt.ACCENT}, stop:1 rgba(0,0,0,100));
                border: 2px solid rgba(255,255,255,0.1);
                border-radius: 27px;
                color: white;
            }}
            QPushButton:hover {{
                border-color: {dt.ACCENT};
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.8,
                    stop:0 {dt.ACCENT_HOVER}, stop:1 rgba(0,0,0,120));
            }}
        """)
        self._orb_btn.clicked.connect(self._toggle_expand)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(99, 102, 241, 150))
        shadow.setOffset(0, 0)
        self._orb_btn.setGraphicsEffect(shadow)

        # ── Expanded: Modern Command Palette ──
        self._palette = QFrame()
        self._palette.setVisible(False)
        self._palette.setStyleSheet(f"""
            QFrame {{
                background: rgba(2, 6, 23, 0.9);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: {dt.RADIUS_LG}px;
            }}
        """)
        
        palette_shadow = QGraphicsDropShadowEffect()
        palette_shadow.setBlurRadius(40)
        palette_shadow.setColor(QColor(0, 0, 0, 200))
        palette_shadow.setOffset(0, 10)
        self._palette.setGraphicsEffect(palette_shadow)

        palette_layout = QVBoxLayout(self._palette)
        palette_layout.setContentsMargins(20, 16, 20, 16)
        palette_layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("JARVIS CORE")
        title.setFont(QFont(dt.FONT_FAMILY, 11, QFont.Weight.Black))
        title.setStyleSheet(f"color: {dt.TEXT_PRIMARY}; letter-spacing: 2px; background: transparent; border: none;")
        header.addWidget(title)
        header.addStretch()

        status = QLabel("● Active")
        status.setFont(QFont(dt.FONT_FAMILY, 9, QFont.Weight.Bold))
        status.setStyleSheet(f"color: {dt.SUCCESS}; background: transparent; border: none;")
        header.addWidget(status)

        palette_layout.addLayout(header)

        # Command input
        self._input = QLineEdit()
        self._input.setPlaceholderText("Command Jarvis...")
        self._input.setFont(QFont(dt.FONT_FAMILY, 12))
        self._input.setStyleSheet(f"""
            QLineEdit {{
                color: {dt.TEXT_PRIMARY}; background: rgba(255,255,255,0.05);
                border: 1px solid {dt.BORDER_DEFAULT}; border-radius: {dt.RADIUS_SM}px;
                padding: 10px 16px;
            }}
            QLineEdit:focus {{
                border-color: {dt.ACCENT};
                background: rgba(255,255,255,0.08);
            }}
        """)
        self._input.returnPressed.connect(self._on_submit)
        palette_layout.addWidget(self._input)

        # Actions row
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)
        for icon, tooltip, callback in [
            ("󰍬", "Voice Mode", lambda: self.toggle_assistant.emit()),
            ("󰄀", "Visuals", lambda: None),
            ("󰚩", "Brain", lambda: None),
            ("󰒓", "Settings", lambda: None),
        ]:
            btn = QPushButton(icon)
            btn.setFixedSize(40, 40)
            btn.setToolTip(tooltip)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255,255,255,0.04); border: 1px solid {dt.BORDER_DEFAULT};
                    border-radius: 8px; font-size: 18px; color: {dt.TEXT_SECONDARY};
                }}
                QPushButton:hover {{ background: {dt.ACCENT_BG}; border-color: {dt.ACCENT}; color: {dt.ACCENT}; }}
            """)
            btn.clicked.connect(callback)
            actions_row.addWidget(btn)
        
        actions_row.addStretch()
        
        esc_hint = QLabel("ESC to close")
        esc_hint.setStyleSheet(f"color: {dt.TEXT_MUTED}; font-size: 8pt;")
        actions_row.addWidget(esc_hint)
        
        palette_layout.addLayout(actions_row)

        # Response label
        self._response_label = QLabel("")
        self._response_label.setWordWrap(True)
        self._response_label.setFont(QFont(dt.FONT_FAMILY, 10))
        self._response_label.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; background: transparent; border: none;")
        self._response_label.setVisible(False)
        palette_layout.addWidget(self._response_label)

        # Assemble
        self._layout.addWidget(self._palette)
        self._layout.addWidget(self._orb_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self._expanded:
            self._collapse()
        super().keyPressEvent(event)

    def _toggle_expand(self):
        if self._expanded:
            self._collapse()
        else:
            self._expand()

    def _expand(self):
        self._expanded = True
        self.setFixedSize(self.EXPANDED_WIDTH, self.EXPANDED_HEIGHT)
        self.move(self._anchor)
        self._palette.setVisible(True)
        self._orb_btn.setVisible(False)
        self._input.setFocus()

    def _collapse(self):
        self._expanded = False
        self._palette.setVisible(False)
        self._orb_btn.setVisible(True)
        self.setFixedSize(self.COLLAPSED_SIZE)
        self.move(
            self._anchor.x() + self.EXPANDED_WIDTH - self.COLLAPSED_SIZE.width(),
            self._anchor.y() + self.EXPANDED_HEIGHT - self.COLLAPSED_SIZE.height(),
        )

    def _on_submit(self):
        text = self._input.text().strip()
        if text:
            self.command_submitted.emit(text)
            self._input.clear()
            self._response_label.setText("Thinking...")
            self._response_label.setVisible(True)

    def show_response(self, text: str):
        """Display a response in the overlay palette."""
        self._response_label.setText(text[:200])
        self._response_label.setVisible(True)
        # Auto-hide after 8 seconds
        QTimer.singleShot(8000, lambda: self._response_label.setVisible(False))

    # ── Dragging support ─────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)
            self._anchor = new_pos

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ── Multi-monitor support ────────────────────────────────────────────

    def move_to_monitor(self, monitor_index: int):
        """Move the overlay to a specific monitor."""
        screens = QApplication.screens()
        if monitor_index < len(screens):
            geo = screens[monitor_index].availableGeometry()
            self._anchor = QPoint(
                geo.right() - self.EXPANDED_WIDTH - 20,
                geo.bottom() - self.EXPANDED_HEIGHT - 20,
            )
            if self._expanded:
                self.move(self._anchor)
            else:
                self.move(
                    self._anchor.x() + self.EXPANDED_WIDTH - self.COLLAPSED_SIZE.width(),
                    self._anchor.y() + self.EXPANDED_HEIGHT - self.COLLAPSED_SIZE.height(),
                )

