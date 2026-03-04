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
    """QFrame with glassmorphic look."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: rgba(22, 27, 34, 0.65);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: {dt.RADIUS_LG}px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)


# ═══════════════════════════════════════════════════════════════════════════════
#  Sidebar
# ═══════════════════════════════════════════════════════════════════════════════

_NAV_ICONS = {
    "Home": "🏠", "Models": "🧩", "Local LLMs": "🖥", "API Keys": "🔑", "History": "🕒",
}

class SidebarButton(QPushButton):
    def __init__(self, text, icon_char=""):
        super().__init__(f"  {icon_char}   {text}")
        self.setCheckable(True)
        self.setFixedHeight(38)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_BODY))
        self.setStyleSheet(f"""
            QPushButton {{
                color: {dt.TEXT_SECONDARY}; background: transparent;
                border: none; border-radius: {dt.RADIUS}px;
                text-align: left; padding-left: 8px;
            }}
            QPushButton:hover {{
                color: {dt.TEXT_PRIMARY}; background: rgba(255,255,255,0.04);
            }}
            QPushButton:checked {{
                color: {dt.ACCENT}; background: rgba(19, 91, 236, 0.12); font-weight: bold;
            }}
        """)


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Dashboard
# ═══════════════════════════════════════════════════════════════════════════════

class JarvisDashboard(QMainWindow):
    """Primary Jarvis Windows App — glassmorphic dashboard."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis AI")
        self.resize(1280, 820)
        self.setMinimumSize(1024, 600)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None
        self._assistant_proc = None

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
        root = QWidget()
        root.setObjectName("DashRoot")
        root.setStyleSheet(f"""
            QWidget#DashRoot {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #0a0e17, stop:0.4 #0e1420, stop:0.7 #111927, stop:1 #0d1220);
                border-radius: {dt.RADIUS_LG}px;
                border: 1px solid {dt.BORDER_SUBTLE};
            }}
            QLabel {{ color: {dt.TEXT_PRIMARY}; font-family: '{dt.FONT_FAMILY}'; }}
        """)
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
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
        bar.setFixedHeight(50)
        bar.setStyleSheet(f"""
            QFrame {{
                background: rgba(10, 14, 23, 0.92);
                border-bottom: 1px solid {dt.BORDER_SUBTLE};
                border-top-left-radius: {dt.RADIUS_LG}px;
                border-top-right-radius: {dt.RADIUS_LG}px;
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 12, 0)

        brand = QLabel("⫸  Jarvis AI")
        brand.setFont(QFont(dt.FONT_FAMILY, 13, QFont.Weight.Bold))
        brand.setStyleSheet(f"color: {dt.TEXT_PRIMARY}; border: none; background: transparent;")
        layout.addWidget(brand)
        layout.addStretch()

        search = QLineEdit()
        search.setPlaceholderText("🔍  Search commands, settings...")
        search.setFixedSize(280, 30)
        search.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_SMALL))
        search.setStyleSheet(f"""
            QLineEdit {{
                color: {dt.TEXT_SECONDARY}; background: rgba(255,255,255,0.04);
                border: 1px solid {dt.BORDER_DEFAULT}; border-radius: 15px; padding: 0 14px;
            }}
            QLineEdit:focus {{ border-color: {dt.ACCENT}; color: {dt.TEXT_PRIMARY}; }}
        """)
        layout.addWidget(search)
        layout.addStretch()

        for char, slot, hover_color in [
            ("─", self.showMinimized, dt.TEXT_MUTED),
            ("□", self._toggle_maximize, dt.TEXT_MUTED),
            ("✕", self.close, dt.ERROR),
        ]:
            btn = QPushButton(char)
            btn.setFixedSize(30, 30)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none; color: {dt.TEXT_SECONDARY};
                    font-size: 13pt; border-radius: 4px;
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
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background: rgba(13, 17, 23, 0.85);
                border-right: 1px solid {dt.BORDER_SUBTLE};
                border-bottom-left-radius: {dt.RADIUS_LG}px;
            }}
        """)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 16, 10, 16)
        layout.setSpacing(4)

        hub = QLabel("  🤖  AI Hub\n        v2.1.0")
        hub.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_BODY, QFont.Weight.Bold))
        hub.setStyleSheet(f"color: {dt.TEXT_PRIMARY}; margin-bottom: 12px;")
        layout.addWidget(hub)

        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {dt.BORDER_DEFAULT};")
        layout.addWidget(sep)
        layout.addSpacing(8)

        self.nav_buttons = {}
        for i, name in enumerate(["Home", "Models", "Local LLMs", "API Keys", "History"]):
            btn = SidebarButton(name, _NAV_ICONS.get(name, ""))
            btn.clicked.connect(lambda checked, idx=i, b=btn: self._switch_page(idx, b))
            layout.addWidget(btn)
            self.nav_buttons[name] = btn

        layout.addStretch()

        launch_btn = QPushButton("▶  Launch Assistant")
        launch_btn.setFixedHeight(40)
        launch_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        launch_btn.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_BODY, QFont.Weight.Bold))
        launch_btn.setStyleSheet(f"""
            QPushButton {{
                color: {dt.TEXT_ON_ACCENT};
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {dt.ACCENT}, stop:1 #1e88e5);
                border: none; border-radius: {dt.RADIUS}px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {dt.ACCENT_HOVER}, stop:1 #42a5f5);
            }}
            QPushButton:pressed {{ background: {dt.ACCENT_PRESSED}; }}
        """)
        launch_btn.clicked.connect(self._launch_assistant)
        layout.addWidget(launch_btn)

        ver = QLabel("  Jarvis v1.2.0")
        ver.setStyleSheet(f"color: {dt.TEXT_MUTED}; font-size: {dt.FONT_SIZE_CAPTION}pt; margin-top: 4px;")
        layout.addWidget(ver)

        return sidebar

    def _switch_page(self, index, btn):
        for b in self.nav_buttons.values():
            b.setChecked(False)
        btn.setChecked(True)
        self.stack.setCurrentIndex(index)

    # ── Launch Assistant ─────────────────────────────────────────────────────

    def _launch_assistant(self):
        bat = os.path.join(PROJECT_ROOT, "run_jarvis.bat")
        if os.path.isfile(bat):
            self._assistant_proc = subprocess.Popen(
                ["cmd", "/c", "start", "Jarvis Assistant", bat],
                cwd=PROJECT_ROOT, creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        else:
            self._assistant_proc = subprocess.Popen(
                [sys.executable, "-m", "Jarvis.main"],
                cwd=PROJECT_ROOT, creationflags=subprocess.CREATE_NEW_CONSOLE
            )

    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: Home
    # ══════════════════════════════════════════════════════════════════════════

    def _build_home(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(dt.scrollarea_style() + "QScrollArea { background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(20)

        # ── Hero Card ──
        hero = GlassmorphicFrame()
        hero.setMinimumHeight(220)
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(28, 20, 28, 20)
        hl.setSpacing(8)

        badge_row = QHBoxLayout()
        badge = QLabel("  ● Active")
        badge.setFixedSize(80, 24)
        badge.setStyleSheet(f"""
            background: {dt.SUCCESS_BG}; color: {dt.SUCCESS};
            border-radius: 12px; font-size: {dt.FONT_SIZE_SMALL}pt;
            font-weight: bold; padding-left: 4px;
        """)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_row.addWidget(badge)
        badge_row.addStretch()

        mic_btn = QPushButton("🎙")
        mic_btn.setFixedSize(42, 42)
        mic_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        mic_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 21px; font-size: 18pt;
            }}
            QPushButton:hover {{ background: rgba(19,91,236,0.2); }}
        """)
        mic_btn.clicked.connect(self._launch_assistant)
        badge_row.addWidget(mic_btn)
        hl.addLayout(badge_row)

        model_name = _active_model_name()
        title = QLabel(f"{model_name} is listening...")
        title.setFont(QFont(dt.FONT_FAMILY, 24, QFont.Weight.Bold))
        title.setStyleSheet("color: white; border: none; background: transparent;")
        hl.addWidget(title)

        wave = QFrame()
        wave.setFixedHeight(70)
        wave.setStyleSheet("""
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0.5,
                stop:0 rgba(88,166,255,0.15), stop:0.3 rgba(188,140,255,0.2),
                stop:0.6 rgba(0,255,159,0.15), stop:1 rgba(88,166,255,0.1));
            border-radius: 8px;
        """)
        hl.addWidget(wave)

        last_cmd = QLabel('"Show me the latest local models available..."')
        last_cmd.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_BODY))
        last_cmd.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; border: none; background: transparent;")
        hl.addWidget(last_cmd)

        layout.addWidget(hero)

        # ── Stat Cards ──
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)

        self._spark_cpu = SparkLine(color="#3fb950", dot_color="#3fb950")
        self._spark_net = SparkLine(color="#bc8cff", dot_color="#e040fb")

        for label, val, unit, spark in [
            ("⚡  System Load", "14", "%",   self._spark_cpu),
            ("📡  Network Ping", "24", "ms", self._spark_net),
            ("🤖  Active Model", model_name, "",  None),
        ]:
            card = GlassmorphicFrame()
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card.setFixedHeight(100)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)

            top = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_SMALL))
            lbl.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; background: transparent; border: none;")
            top.addWidget(lbl)
            top.addStretch()
            if spark:
                dot = QLabel("●")
                dot.setStyleSheet(f"color: {spark._color.name()}; font-size: 8pt; background: transparent; border: none;")
                top.addWidget(dot)
            cl.addLayout(top)

            bottom = QHBoxLayout()
            v_lbl = QLabel(f"<span style='font-size:22pt;font-weight:700;'>{val}</span>"
                           f"<span style='font-size:11pt;color:{dt.TEXT_SECONDARY};'>{unit}</span>")
            v_lbl.setStyleSheet("background: transparent; border: none;")
            bottom.addWidget(v_lbl)
            bottom.addStretch()
            if spark:
                bottom.addWidget(spark)
            cl.addLayout(bottom)

            stats_row.addWidget(card)

        layout.addLayout(stats_row)

        # ── Quick Start Services ──
        qs = QLabel("Quick Start Services")
        qs.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H2, QFont.Weight.Bold))
        layout.addWidget(qs)

        svc_row = QHBoxLayout()
        svc_row.setSpacing(16)
        for icon, name, desc, color in [
            ("🎨", "Image Generation", "Create images from text descriptions using DALL-E 3.", "#e040fb"),
            ("⟨/⟩", "Code Assistant", "Get help with programming, debugging, and review.", "#58a6ff"),
            ("🌐", "Web Search", "Search the web for real-time information and news.", "#ffab40"),
        ]:
            card = GlassmorphicFrame()
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card.setFixedHeight(130)
            card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 16, 16, 16)

            ic = QLabel(icon)
            ic.setFixedSize(40, 40)
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c = QColor(color)
            ic.setStyleSheet(f"background: rgba({c.red()},{c.green()},{c.blue()},0.15); border-radius: 12px; font-size: 18pt; border: none;")
            cl.addWidget(ic)

            nl = QLabel(name)
            nl.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H3, QFont.Weight.Bold))
            nl.setStyleSheet("background: transparent; border: none;")
            cl.addWidget(nl)

            dl = QLabel(desc)
            dl.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; font-size: {dt.FONT_SIZE_SMALL}pt; background: transparent; border: none;")
            dl.setWordWrap(True)
            cl.addWidget(dl)

            svc_row.addWidget(card)

        layout.addLayout(svc_row)
        layout.addStretch()
        page.setWidget(content)
        return page

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
