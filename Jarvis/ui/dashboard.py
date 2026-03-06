"""
Jarvis Dashboard — Primary Windows Application
================================================
Glassmorphic desktop dashboard matching the Stitch design system.
Opened by clicking the app icon. The voice assistant is launched
from the "Launch Assistant" button which runs run_jarvis.bat.
"""
import sys
import os
import math
import random
import subprocess
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QPushButton, QLabel, QFrame, QScrollArea, QGridLayout, QProgressBar,
    QCheckBox, QComboBox, QLineEdit, QGraphicsDropShadowEffect, QSizePolicy,
    QApplication
)
from PyQt6.QtCore import Qt, QTimer, QSize, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QLinearGradient, QRadialGradient,
    QCursor, QPainterPath, QFontDatabase, QConicalGradient
)

from Jarvis.ui import design_tokens as dt
from Jarvis.config import (
    LLM_PROVIDER, OLLAMA_MODEL, GEMINI_MODEL, GROQ_MODEL, GROK_MODEL,
    STT_PROVIDER, TTS_ENGINE, PIPELINE_MODE, BARGE_IN_ENABLED,
    RESPONSE_STYLE, DEFAULT_PERSONA, TTS_VOICE, GEMINI_API_KEY, GROQ_API_KEY
)

# ── Helper: get the project root (where run_jarvis.bat lives) ────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ASSETS_DIR = os.path.join(PROJECT_ROOT, "Jarvis", "assets")

def _active_model_name():
    return {
        "gemini": GEMINI_MODEL, "groq": GROQ_MODEL,
        "ollama": OLLAMA_MODEL, "grok": GROK_MODEL,
    }.get(LLM_PROVIDER, OLLAMA_MODEL)


# ═══════════════════════════════════════════════════════════════════════════════
#  Custom Painted Widgets
# ═══════════════════════════════════════════════════════════════════════════════

class SparkLine(QWidget):
    """Tiny line-chart widget drawn with QPainter."""
    def __init__(self, data=None, color="#58a6ff", dot_color=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 32)
        self._color = QColor(color)
        self._dot = QColor(dot_color) if dot_color else QColor(color)
        self._data = data or [random.uniform(0.2, 0.9) for _ in range(16)]

    def set_data(self, data):
        self._data = data
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        margin = 4
        n = len(self._data)
        dx = (w - 2 * margin) / max(n - 1, 1)

        path = QPainterPath()
        points = []
        for i, v in enumerate(self._data):
            x = margin + i * dx
            y = h - margin - v * (h - 2 * margin)
            points.append(QPointF(x, y))
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        pen = QPen(self._color, 1.5)
        p.setPen(pen)
        p.drawPath(path)

        if points:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self._dot))
            p.drawEllipse(points[-1], 3, 3)
        p.end()


class DonutChart(QWidget):
    """Circular donut gauge widget."""
    def __init__(self, value=0, max_val=100, parent=None):
        super().__init__(parent)
        self.setFixedSize(140, 140)
        self._value = value
        self._max = max_val

    def set_value(self, v):
        self._value = v
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = min(self.width(), self.height())
        rect = QRectF(10, 10, s - 20, s - 20)
        thickness = 10

        pen_bg = QPen(QColor(dt.BORDER_DEFAULT), thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen_bg)
        p.drawArc(rect, 0, 360 * 16)

        frac = min(self._value / max(self._max, 1), 1.0)
        span = int(frac * 360 * 16)

        grad = QConicalGradient(rect.center(), 90)
        grad.setColorAt(0, QColor("#58a6ff"))
        grad.setColorAt(0.5, QColor("#bc8cff"))
        grad.setColorAt(1, QColor("#58a6ff"))

        pen_val = QPen(QBrush(grad), thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen_val)
        p.drawArc(rect, 90 * 16, -span)

        p.setPen(QColor(dt.TEXT_PRIMARY))
        p.setFont(QFont(dt.FONT_FAMILY, 18, QFont.Weight.Bold))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{int(frac * 100)}%")
        p.end()


class GlassmorphicFrame(QFrame):
    """QFrame with refined world-class glassmorphic look."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-top: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: {dt.RADIUS_LG}px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(50)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 12)
        self.setGraphicsEffect(shadow)


# ═══════════════════════════════════════════════════════════════════════════════
#  Sidebar
# ═══════════════════════════════════════════════════════════════════════════════

_NAV_ICONS = {
    "Home": "󰋜", "Models": "󰙨", "Local LLMs": "󰚗", "API Keys": "󰌆", "History": "󰄉",
}

class SidebarButton(QPushButton):
    def __init__(self, text, icon_char=""):
        # Use icon char if available, otherwise fallback
        display_text = f"  {icon_char}   {text}" if icon_char else f"    {text}"
        super().__init__(display_text)
        self.setCheckable(True)
        self.setFixedHeight(44)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_BODY))
        self.setStyleSheet(f"""
            QPushButton {{
                color: {dt.TEXT_SECONDARY}; background: transparent;
                border: none; border-radius: {dt.RADIUS_SM}px;
                text-align: left; padding-left: 12px;
                margin: 2px 0;
            }}
            QPushButton:hover {{
                color: {dt.TEXT_PRIMARY}; background: rgba(255,255,255,0.05);
            }}
            QPushButton:checked {{
                color: {dt.TEXT_PRIMARY}; background: {dt.ACCENT_BG}; 
                border-left: 3px solid {dt.ACCENT};
                padding-left: 9px;
                font-weight: 600;
            }}
        """)


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Dashboard
# ═══════════════════════════════════════════════════════════════════════════════

class DashRoot(QWidget):
    """Root widget that paints a sophisticated background."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DashRoot")
        self._bg_pixmap = None
        img_path = os.path.join(ASSETS_DIR, "bg.png")
        if os.path.isfile(img_path):
            from PyQt6.QtGui import QPixmap
            self._bg_pixmap = QPixmap(img_path)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()

        # Rounded corners for the whole window
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), dt.RADIUS_LG, dt.RADIUS_LG)
        p.setClipPath(path)

        if self._bg_pixmap and not self._bg_pixmap.isNull():
            # Scale to cover (crop excess)
            pm_size = self._bg_pixmap.size()
            x_ratio = rect.width() / pm_size.width()
            y_ratio = rect.height() / pm_size.height()
            scale = max(x_ratio, y_ratio)
            
            scaled_w = int(pm_size.width() * scale)
            scaled_h = int(pm_size.height() * scale)
            x_off = (rect.width() - scaled_w) // 2
            y_off = (rect.height() - scaled_h) // 2
            
            p.drawPixmap(x_off, y_off, scaled_w, scaled_h, self._bg_pixmap)
            
            # Apply dark/subtle overlay
            alpha = getattr(self, '_overlay_alpha', 0.4)
            p.fillRect(rect, QColor(2, 6, 23, int(alpha * 255)))
        else:
            # Fallback sophisticated gradient
            grad = QLinearGradient(0, 0, rect.width(), rect.height())
            grad.setColorAt(0, QColor("#020617"))
            grad.setColorAt(1, QColor("#0f172a"))
            p.fillRect(rect, grad)

        # Draw a very subtle inner glow/border
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 20), 1))
        p.drawPath(path)
        p.end()

class JarvisDashboard(QMainWindow):
    """Primary Jarvis Windows App — world-class dashboard."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis AI")
        self.resize(1280, 840)
        self.setMinimumSize(1024, 720)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None
        self._assistant_proc = None

        self._opacity_overlay = 0.4 # Default dimming for a professional look

        screen = QApplication.primaryScreen().geometry() if QApplication.primaryScreen() else None
        if screen:
            self.move((screen.width() - self.width()) // 2,
                       (screen.height() - self.height()) // 2)

        self._build_ui()

        self._sparkline_timer = QTimer()
        self._sparkline_timer.timeout.connect(self._refresh_sparklines)
        self._sparkline_timer.start(2000)

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        self.root = DashRoot()
        self.root._overlay_alpha = self._opacity_overlay
        self.root.setStyleSheet(f"""
            QLabel {{ color: {dt.TEXT_PRIMARY}; font-family: '{dt.FONT_FAMILY}'; }}
        """)
        self.setCentralWidget(self.root)

        outer = QVBoxLayout(self.root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_title_bar())

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        body_layout.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: transparent;")
        self.pages = {}
        for name, builder in [
            ("Home",       self._build_home),
            ("Models",     self._build_models),
            ("Local LLMs", self._build_local_llms),
            ("API Keys",   self._build_api_keys),
            ("History",    self._build_history),
        ]:
            page = builder()
            self.stack.addWidget(page)
            self.pages[name] = page

        body_layout.addWidget(self.stack)
        outer.addWidget(body)

        self._switch_page(0, self.nav_buttons["Home"])

    # ── Title Bar ────────────────────────────────────────────────────────────

    def _build_title_bar(self):
        bar = QFrame()
        bar.setFixedHeight(dt.HEADER_HEIGHT)
        bar.setStyleSheet(f"""
            QFrame {{
                background: rgba(2, 6, 23, 0.6);
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                border-top-left-radius: {dt.RADIUS_LG}px;
                border-top-right-radius: {dt.RADIUS_LG}px;
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 16, 0)

        brand = QLabel("JARVIS")
        brand.setFont(QFont(dt.FONT_FAMILY, 14, QFont.Weight.Black))
        brand.setStyleSheet(f"color: {dt.TEXT_PRIMARY}; letter-spacing: 2px; border: none; background: transparent;")
        layout.addWidget(brand)
        layout.addStretch()

        search_container = QFrame()
        search_container.setFixedSize(320, 34)
        search_container.setStyleSheet(f"background: rgba(255,255,255,0.04); border: 1px solid {dt.BORDER_DEFAULT}; border-radius: 17px;")
        sl = QHBoxLayout(search_container)
        sl.setContentsMargins(12, 0, 12, 0)
        
        search = QLineEdit()
        search.setPlaceholderText("Search commands or settings...")
        search.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_BODY))
        search.setStyleSheet("color: white; background: transparent; border: none;")
        sl.addWidget(search)
        layout.addWidget(search_container)
        layout.addStretch()

        for char, slot, hover_color in [
            ("󰖰", self.showMinimized, "rgba(255,255,255,0.1)"),
            ("󰖲", self._toggle_maximize, "rgba(255,255,255,0.1)"),
            ("󰖭", self.close, dt.ERROR),
        ]:
            btn = QPushButton(char)
            btn.setFixedSize(32, 32)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none; color: {dt.TEXT_SECONDARY};
                    font-size: 14pt; border-radius: 6px;
                }}
                QPushButton:hover {{ background: {hover_color}; color: white; }}
            """)
            btn.clicked.connect(slot)
            layout.addWidget(btn)

        return bar

    def _toggle_maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    # ── Sidebar ──────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setFixedWidth(dt.SIDEBAR_WIDTH)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background: rgba(2, 6, 23, 0.4);
                border-right: 1px solid rgba(255, 255, 255, 0.05);
                border-bottom-left-radius: {dt.RADIUS_LG}px;
            }}
        """)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(6)

        hub = QLabel("  Jarvis AI\n  <span style='color:{dt.TEXT_MUTED}; font-size:9pt;'>Advanced Core v2.2</span>")
        hub.setFont(QFont(dt.FONT_FAMILY, 12, QFont.Weight.Bold))
        hub.setStyleSheet(f"color: {dt.TEXT_PRIMARY}; margin-bottom: 20px;")
        layout.addWidget(hub)

        self.nav_buttons = {}
        for i, name in enumerate(["Home", "Models", "Local LLMs", "API Keys", "History"]):
            btn = SidebarButton(name, _NAV_ICONS.get(name, ""))
            btn.clicked.connect(lambda checked, idx=i, b=btn: self._switch_page(idx, b))
            layout.addWidget(btn)
            self.nav_buttons[name] = btn

        layout.addStretch()

        launch_btn = QPushButton("󰐊  Launch Assistant")
        launch_btn.setFixedHeight(46)
        launch_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        launch_btn.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_BODY, QFont.Weight.Bold))
        launch_btn.setStyleSheet(f"""
            QPushButton {{
                color: {dt.TEXT_ON_ACCENT};
                background: {dt.ACCENT};
                border: none; border-radius: {dt.RADIUS_SM}px;
            }}
            QPushButton:hover {{
                background: {dt.ACCENT_HOVER};
            }}
            QPushButton:pressed {{ background: {dt.ACCENT_PRESSED}; }}
        """)
        launch_btn.clicked.connect(self._launch_assistant)
        layout.addWidget(launch_btn)

        ver = QLabel("System Status: Nominal")
        ver.setStyleSheet(f"color: {dt.SUCCESS}; font-size: 8pt; margin-top: 8px; font-weight: bold;")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ver)

        return sidebar

    def _switch_page(self, index, btn):
        for b in self.nav_buttons.values():
            b.setChecked(False)
        btn.setChecked(True)
        self.stack.setCurrentIndex(index)

    # ── Launch Assistant ─────────────────────────────────────────────────────

    def _launch_assistant(self):
        python_exe = sys.executable
        script_path = os.path.join(PROJECT_ROOT, "Jarvis", "main.py")
        subprocess.Popen(
            [python_exe, script_path, "--assistant"],
            cwd=PROJECT_ROOT,
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: Home
    # ══════════════════════════════════════════════════════════════════════════

    def _build_home(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(dt.scrollarea_style())

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(dt.SPACING_XL, dt.SPACING_LG, dt.SPACING_XL, dt.SPACING_XL)
        layout.setSpacing(dt.SPACING_XL)

        # ── Hero Card ──
        hero = GlassmorphicFrame()
        hero.setMinimumHeight(240)
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(dt.SPACING_XXL, dt.SPACING_XL, dt.SPACING_XXL, dt.SPACING_XL)
        hl.setSpacing(12)

        badge_row = QHBoxLayout()
        badge = QLabel("  ●  System Active")
        badge.setFixedSize(120, 26)
        badge.setStyleSheet(f"""
            background: {dt.SUCCESS_BG}; color: {dt.SUCCESS};
            border-radius: 13px; font-size: 9pt;
            font-weight: bold; padding-left: 8px;
        """)
        badge.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        badge_row.addWidget(badge)
        badge_row.addStretch()

        mic_btn = QPushButton("󰍬")
        mic_btn.setFixedSize(48, 48)
        mic_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        mic_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 24px; font-size: 20pt; color: {dt.ACCENT};
            }}
            QPushButton:hover {{ background: {dt.ACCENT_BG}; border-color: {dt.ACCENT}; }}
        """)
        mic_btn.clicked.connect(self._launch_assistant)
        badge_row.addWidget(mic_btn)
        hl.addLayout(badge_row)

        model_name = _active_model_name()
        title = QLabel(f"Welcome back. {model_name} is ready.")
        title.setFont(QFont(dt.FONT_FAMILY, 28, QFont.Weight.Black))
        title.setStyleSheet("color: white; border: none; background: transparent;")
        hl.addWidget(title)

        subtitle = QLabel("How can I assist you with your projects today?")
        subtitle.setFont(QFont(dt.FONT_FAMILY, 14))
        subtitle.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; border: none;")
        hl.addWidget(subtitle)

        hl.addSpacing(10)
        
        last_cmd = QLabel("󰜎  Recent activity: Executed codebase investigation")
        last_cmd.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_BODY))
        last_cmd.setStyleSheet(f"color: {dt.TEXT_MUTED}; border: none;")
        hl.addWidget(last_cmd)

        layout.addWidget(hero)

        # ── Stat Cards ──
        stats_row = QHBoxLayout()
        stats_row.setSpacing(dt.SPACING_LG)

        self._spark_cpu = SparkLine(color=dt.SUCCESS, dot_color=dt.SUCCESS)
        self._spark_net = SparkLine(color=dt.INFO, dot_color=dt.INFO)

        for label, val, unit, spark in [
            ("󰻠  CPU LOAD", "12", "%",   self._spark_cpu),
            ("󰖩  LATENCY", "18", "ms", self._spark_net),
            ("󰚩  AI CORE", "V2.2", "",  None),
        ]:
            card = GlassmorphicFrame()
            card.setFixedHeight(120)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(dt.SPACING_LG, dt.SPACING_MD, dt.SPACING_LG, dt.SPACING_MD)

            top = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_CAPTION, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color: {dt.TEXT_MUTED}; letter-spacing: 1px;")
            top.addWidget(lbl)
            top.addStretch()
            cl.addLayout(top)

            bottom = QHBoxLayout()
            v_lbl = QLabel(f"<span style='font-size:24pt;font-weight:900;'>{val}</span>"
                           f"<span style='font-size:12pt;color:{dt.TEXT_SECONDARY}; font-weight:400;'> {unit}</span>")
            bottom.addWidget(v_lbl)
            bottom.addStretch()
            if spark:
                bottom.addWidget(spark)
            cl.addLayout(bottom)

            stats_row.addWidget(card)

        layout.addLayout(stats_row)

        # ── Quick Actions ──
        qa_header = QHBoxLayout()
        qa_label = QLabel("Recommended Actions")
        qa_label.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H2, QFont.Weight.Bold))
        qa_header.addWidget(qa_label)
        qa_header.addStretch()
        
        op_lbl = QLabel("Glass Opacity:")
        op_lbl.setStyleSheet(f"color: {dt.TEXT_MUTED}; font-size: 8pt;")
        qa_header.addWidget(op_lbl)
        
        from PyQt6.QtWidgets import QSlider
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(5, 95)
        self.opacity_slider.setValue(40)
        self.opacity_slider.setFixedWidth(100)
        self.opacity_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {dt.ACCENT}; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }}
        """)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        qa_header.addWidget(self.opacity_slider)
        layout.addLayout(qa_header)

        svc_row = QHBoxLayout()
        svc_row.setSpacing(dt.SPACING_LG)
        for icon, name, desc, color in [
            ("󰏘", "Creative Mode", "High-fidelity image generation.", "#d946ef"),
            ("󰅩", "Coding Forge", "Specialized coding assistance.", "#3b82f6"),
            ("󰖟", "Knowledge Base", "Real-time web search access.", "#06b6d4"),
        ]:
            card = GlassmorphicFrame()
            card.setFixedHeight(150)
            card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            card.mousePressEvent = lambda e, n=name: self._handle_quick_start(n)
            
            cl = QVBoxLayout(card)
            cl.setContentsMargins(dt.SPACING_LG, dt.SPACING_LG, dt.SPACING_LG, dt.SPACING_LG)

            ic = QLabel(icon)
            ic.setFixedSize(44, 44)
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c = QColor(color)
            ic.setStyleSheet(f"background: rgba({c.red()},{c.green()},{c.blue()},0.1); border-radius: 12px; font-size: 22pt; color: {color}; border: none;")
            cl.addWidget(ic)

            nl = QLabel(name)
            nl.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H3, QFont.Weight.Bold))
            cl.addWidget(nl)

            dl = QLabel(desc)
            dl.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; font-size: 9pt;")
            dl.setWordWrap(True)
            cl.addWidget(dl)

            svc_row.addWidget(card)

        layout.addLayout(svc_row)
        layout.addStretch()
        page.setWidget(content)
        return page


    # ── Utilities ────────────────────────────────────────────────────────────
    
    def _on_opacity_changed(self, value):
        alpha = value / 100.0
        self.root._overlay_alpha = alpha
        self.root.update()

    def _handle_quick_start(self, name):
        if name == "Image Generation":
            self._do_image_gen()
        elif name == "Code Assistant":
            self._do_code_assistant()
        elif name == "Web Search":
            self._do_web_search()

    def _do_image_gen(self):
        from PyQt6.QtWidgets import QInputDialog, QMessageBox, QDialog, QVBoxLayout, QLabel
        from PyQt6.QtGui import QPixmap
        import requests
        
        query, ok = QInputDialog.getText(self, "Image Generation", "Enter image prompt:")
        if ok and query:
            msg = QMessageBox(self)
            msg.setWindowTitle("Generating Image...")
            msg.setText("Please wait while the image is generated...")
            msg.setStandardButtons(QMessageBox.StandardButton.NoButton)
            msg.show()
            QApplication.processEvents()
            
            try:
                # Use Pollinations AI free tier for instant generation as high quality fallback
                url = f"https://image.pollinations.ai/prompt/{query.replace(' ', '%20')}?width=512&height=512&nologo=true"
                resp = requests.get(url, timeout=15)
                msg.accept()
                
                if resp.status_code == 200:
                    pixmap = QPixmap()
                    pixmap.loadFromData(resp.content)
                    d = QDialog(self)
                    d.setWindowTitle("Generated Image")
                    l = QVBoxLayout(d)
                    img = QLabel(); img.setPixmap(pixmap); img.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    txt = QLabel(f'"{query}"'); txt.setStyleSheet("color: white;"); txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    l.addWidget(img); l.addWidget(txt)
                    d.setStyleSheet(f"background: {dt.BG_BASE};")
                    d.exec()
                else:
                    QMessageBox.warning(self, "Error", "Failed to generate image.")
            except Exception as e:
                msg.accept()
                QMessageBox.warning(self, "Error", f"Could not generate image: {e}")

    def _do_code_assistant(self):
        from PyQt6.QtWidgets import QInputDialog
        models = ["gemini-2.0-flash", "llama-3.3-70b-versatile", "gpt-4o", "llama3.2:3b"]
        model, ok = QInputDialog.getItem(self, "Code Assistant", "Select LLM Model:", models, 0, False)
        if ok and model:
            import os
            os.environ["GEMINI_MODEL"] = model
            os.environ["GROQ_MODEL"] = model
            os.environ["OLLAMA_MODEL"] = model
            self._launch_assistant()

    def _do_web_search(self):
        from PyQt6.QtWidgets import QInputDialog, QMessageBox
        from Jarvis.core.web_search import web_search
        
        query, ok = QInputDialog.getText(self, "Web Search", "Enter search query:")
        if ok and query:
            msg = QMessageBox(self)
            msg.setWindowTitle("Searching...")
            msg.setText("Please wait while Jarvis searches the web...")
            msg.setStandardButtons(QMessageBox.StandardButton.NoButton)
            msg.show()
            QApplication.processEvents()
            
            resp = web_search(query, max_results=5)
            msg.accept()
            
            if resp.error:
                QMessageBox.critical(self, "Search Error", resp.error)
            elif resp.results:
                text = f"<h3 style='color: white;'>Results for: {query}</h3>"
                for r in resp.results:
                    text += f"<b><a href='{r.url}' style='color: {dt.INFO};'>{r.title}</a></b><br><span style='color: {dt.TEXT_SECONDARY};'>{r.snippet}</span><br><br>"
                res_box = QMessageBox(self)
                res_box.setWindowTitle("Web Search Results")
                res_box.setTextFormat(Qt.TextFormat.RichText)
                res_box.setText(text)
                res_box.setStyleSheet(f"QMessageBox {{ background: {dt.BG_BASE}; color: {dt.TEXT_PRIMARY}; }}")
                res_box.exec()
            else:
                QMessageBox.information(self, "Web Search", "No results found.")

    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: Models (Cloud Providers)
    # ══════════════════════════════════════════════════════════════════════════

    def _build_models(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(dt.scrollarea_style() + "QScrollArea { background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 20, 24, 24)
        lay.setSpacing(16)

        h = QLabel("Models")
        h.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H1, QFont.Weight.Bold))
        lay.addWidget(h)
        sub = QLabel("Cloud AI providers and model routing configuration.")
        sub.setStyleSheet(f"color: {dt.TEXT_SECONDARY};")
        lay.addWidget(sub)

        for name, models, usage, active in [
            ("OpenAI",        ["GPT-4o", "GPT-3.5-Turbo"],  75, False),
            ("Google Gemini", [GEMINI_MODEL],                50, "gemini" == LLM_PROVIDER),
            ("Groq",          [GROQ_MODEL, "Mixtral 8x7b"],  10, "groq" == LLM_PROVIDER),
            ("Anthropic",     ["Claude 3.5 Sonnet"],          25, False),
        ]:
            card = GlassmorphicFrame()
            cl = QVBoxLayout(card)
            cl.setContentsMargins(20, 16, 20, 16)
            cl.setSpacing(8)

            row = QHBoxLayout()
            n = QLabel(name)
            n.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H3, QFont.Weight.Bold))
            n.setStyleSheet("background: transparent; border: none;")
            row.addWidget(n)
            if active:
                bdg = QLabel(" ACTIVE ")
                bdg.setStyleSheet(f"background: {dt.SUCCESS_BG}; color: {dt.SUCCESS}; border-radius: 4px; font-size: 9pt; font-weight: bold; padding: 2px 6px;")
                row.addWidget(bdg)
            row.addStretch()
            cl.addLayout(row)

            ml = QLabel(", ".join(models))
            ml.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; background: transparent; border: none;")
            cl.addWidget(ml)

            bar = QProgressBar()
            bar.setValue(usage)
            bar.setTextVisible(False)
            bar.setFixedHeight(6)
            bar.setStyleSheet(dt.progress_bar_style(dt.ACCENT if usage < 80 else dt.WARNING))
            cl.addWidget(bar)

            ul = QLabel(f"{usage}% usage limit")
            ul.setStyleSheet(f"color: {dt.TEXT_MUTED}; font-size: {dt.FONT_SIZE_CAPTION}pt; background: transparent; border: none;")
            cl.addWidget(ul)

            lay.addWidget(card)

        lay.addStretch()
        page.setWidget(content)
        return page

    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: Local LLMs
    # ══════════════════════════════════════════════════════════════════════════

    def _build_local_llms(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(dt.scrollarea_style() + "QScrollArea { background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 20, 24, 24)
        lay.setSpacing(16)

        # Hero
        hero = GlassmorphicFrame()
        hero.setMinimumHeight(100)
        hlay = QVBoxLayout(hero)
        hlay.setContentsMargins(28, 20, 28, 20)
        t = QLabel("Local LLM Forge")
        t.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H1, QFont.Weight.Bold))
        t.setStyleSheet("background: transparent; border: none;")
        hlay.addWidget(t)
        s = QLabel("Manage and deploy your advanced local language models with precision.")
        s.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; background: transparent; border: none;")
        hlay.addWidget(s)
        lay.addWidget(hero)

        # Donut charts
        chart_row = QHBoxLayout()
        chart_row.setSpacing(16)

        for title, value, sub_text in [("VRAM Usage", 65, "10.4 / 16 GB"), ("CPU Load", 28, "8 Cores Active")]:
            card = GlassmorphicFrame()
            card.setFixedSize(180, 210)
            vl = QVBoxLayout(card)
            vl.setContentsMargins(12, 12, 12, 12)
            vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tl = QLabel(title)
            tl.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_BODY, QFont.Weight.Bold))
            tl.setStyleSheet("background: transparent; border: none;")
            vl.addWidget(tl, alignment=Qt.AlignmentFlag.AlignCenter)
            donut = DonutChart(value, 100)
            vl.addWidget(donut, alignment=Qt.AlignmentFlag.AlignCenter)
            sl = QLabel(sub_text)
            sl.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; font-size: {dt.FONT_SIZE_SMALL}pt; background: transparent; border: none;")
            vl.addWidget(sl, alignment=Qt.AlignmentFlag.AlignCenter)
            chart_row.addWidget(card)

        chart_row.addStretch()
        lay.addLayout(chart_row)

        # Specimen Cards
        sc_label = QLabel("Specimen Cards")
        sc_label.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H2, QFont.Weight.Bold))
        lay.addWidget(sc_label)

        for name, params, vram, loaded in [
            ("Llama 3 (8B)",   "8.0B", "5.2 GB", True),
            ("Mistral Large",  "8.0B", "5.2 GB", True),
            ("Gemma 7B",       "7.0B", "4.8 GB", False),
        ]:
            card = GlassmorphicFrame()
            cl = QVBoxLayout(card)
            cl.setContentsMargins(20, 16, 20, 16)
            cl.setSpacing(6)

            nl = QLabel(name)
            nl.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H3, QFont.Weight.Bold))
            nl.setStyleSheet("background: transparent; border: none;")
            cl.addWidget(nl)

            info_row = QHBoxLayout()
            left = QLabel(f"Model Type: Transformer\nParameters: {params}\nQuantization: 4-bit\nContext Window: 8K")
            left.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; font-size: {dt.FONT_SIZE_SMALL}pt; background: transparent; border: none;")
            info_row.addWidget(left)

            status_color = dt.SUCCESS if loaded else dt.TEXT_MUTED
            right = QLabel(f"Architecture: Dec-Only\nVRAM Req: {vram}\nStatus: {'Loaded' if loaded else 'Available'}")
            right.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; font-size: {dt.FONT_SIZE_SMALL}pt; background: transparent; border: none;")
            info_row.addWidget(right)
            info_row.addStretch()
            cl.addLayout(info_row)

            br = QHBoxLayout()
            br.addStretch()
            lb = QPushButton("Load" if not loaded else "Unload")
            lb.setStyleSheet(dt.button_primary_style() if not loaded else dt.button_secondary_style())
            lb.setFixedSize(100, 34)
            lb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            br.addWidget(lb)
            cl.addLayout(br)

            lay.addWidget(card)

        lay.addStretch()
        page.setWidget(content)
        return page

    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: API Keys
    # ══════════════════════════════════════════════════════════════════════════

    def _build_api_keys(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(dt.scrollarea_style() + "QScrollArea { background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 20, 24, 24)
        lay.setSpacing(16)

        h = QLabel("API Keys")
        h.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H1, QFont.Weight.Bold))
        lay.addWidget(h)
        sub = QLabel("Manage API credentials. Keys stored locally in .env file.")
        sub.setStyleSheet(f"color: {dt.TEXT_SECONDARY};")
        lay.addWidget(sub)

        for label, val in [
            ("Gemini API Key", GEMINI_API_KEY),
            ("Groq API Key",   GROQ_API_KEY),
            ("Grok API Key",   ""),
        ]:
            card = GlassmorphicFrame()
            cl = QHBoxLayout(card)
            cl.setContentsMargins(20, 14, 20, 14)

            lbl = QLabel(label)
            lbl.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_BODY, QFont.Weight.Bold))
            lbl.setStyleSheet("background: transparent; border: none;")
            cl.addWidget(lbl)
            cl.addStretch()

            inp = QLineEdit()
            inp.setFixedWidth(280)
            inp.setEchoMode(QLineEdit.EchoMode.Password)
            inp.setText(val)
            inp.setStyleSheet(f"""
                QLineEdit {{
                    color: {dt.TEXT_PRIMARY}; background: {dt.BG_BASE};
                    border: 1px solid {dt.BORDER_DEFAULT}; border-radius: {dt.RADIUS}px;
                    padding: 6px 12px; font-family: '{dt.FONT_FAMILY_MONO}';
                }}
                QLineEdit:focus {{ border-color: {dt.ACCENT}; }}
            """)
            cl.addWidget(inp)

            dot = QLabel("●")
            dot.setStyleSheet(f"color: {dt.SUCCESS if val else dt.ERROR}; font-size: 14pt; background: transparent; border: none;")
            cl.addWidget(dot)

            lay.addWidget(card)

        br = QHBoxLayout()
        br.addStretch()
        save = QPushButton("Save Keys")
        save.setStyleSheet(dt.button_primary_style())
        save.setFixedSize(120, 36)
        save.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        br.addWidget(save)
        lay.addLayout(br)

        lay.addStretch()
        page.setWidget(content)
        return page

    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: History
    # ══════════════════════════════════════════════════════════════════════════

    def _build_history(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(dt.scrollarea_style() + "QScrollArea { background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 20, 24, 24)
        lay.setSpacing(12)

        h = QLabel("Interaction History")
        h.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H1, QFont.Weight.Bold))
        lay.addWidget(h)

        colors = {"System": dt.INFO, "Model": dt.ACCENT, "User": "#bc8cff",
                  "Jarvis": dt.SUCCESS, "Action": dt.WARNING}

        for time, tag, text in [
            ("16:02", "System", "Jarvis initialized — all systems nominal"),
            ("16:01", "Model",  f"Loaded {_active_model_name()} on {LLM_PROVIDER}"),
            ("15:58", "User",   "Show me the latest local models available"),
            ("15:58", "Jarvis", "Here are your currently available local models: gemma:2b, llama3.2:3b"),
            ("15:55", "Action", "Executed: spotify play Lo-fi Beats"),
            ("15:50", "User",   "What's the weather today?"),
            ("15:50", "Jarvis", "It's currently 28°C and sunny in your area."),
        ]:
            card = GlassmorphicFrame()
            cl = QHBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)

            tl = QLabel(time)
            tl.setFixedWidth(50)
            tl.setStyleSheet(f"color: {dt.TEXT_MUTED}; font-family: '{dt.FONT_FAMILY_MONO}'; font-size: {dt.FONT_SIZE_SMALL}pt; background: transparent; border: none;")
            cl.addWidget(tl)

            tagl = QLabel(tag)
            tagl.setFixedWidth(60)
            tagl.setStyleSheet(f"color: {colors.get(tag, dt.TEXT_SECONDARY)}; font-weight: bold; font-size: {dt.FONT_SIZE_SMALL}pt; background: transparent; border: none;")
            cl.addWidget(tagl)

            msg = QLabel(text)
            msg.setStyleSheet(f"color: {dt.TEXT_PRIMARY}; background: transparent; border: none;")
            msg.setWordWrap(True)
            cl.addWidget(msg)

            lay.addWidget(card)

        lay.addStretch()
        page.setWidget(content)
        return page

    # ── Sparkline Refresh ────────────────────────────────────────────────────

    def _refresh_sparklines(self):
        for spark in (self._spark_cpu, self._spark_net):
            data = spark._data[1:] + [random.uniform(0.15, 0.95)]
            spark.set_data(data)

    # ── Window Dragging ──────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 50:
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._drag_pos:
            self.move(self.pos() + event.globalPosition().toPoint() - self._drag_pos)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
