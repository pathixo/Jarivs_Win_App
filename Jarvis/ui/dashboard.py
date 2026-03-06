"""
Jarvis Dashboard — Primary Windows Application
================================================
Official desktop dashboard for Jarvis AI.
Designed with a professional, segmented layout for clear status monitoring 
and rapid tool access.
"""
import sys
import os
import random
import subprocess
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QPushButton, QLabel, QFrame, QScrollArea, QGridLayout, QProgressBar,
    QLineEdit, QGraphicsDropShadowEffect, QApplication, QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QSize, QRectF, QPointF
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QLinearGradient,
    QCursor, QPainterPath, QIcon
)

from Jarvis.ui import design_tokens as dt
from Jarvis.config import (
    LLM_PROVIDER, OLLAMA_MODEL, GEMINI_MODEL, GROQ_MODEL, GROK_MODEL,
    GEMINI_API_KEY, GROQ_API_KEY
)

# ── Helper: get the project root ─────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def _active_model_name():
    return {
        "gemini": GEMINI_MODEL, "groq": GROQ_MODEL,
        "ollama": OLLAMA_MODEL, "grok": GROK_MODEL,
    }.get(LLM_PROVIDER, OLLAMA_MODEL)


# ── Professional Backdrop ──────────────────────────────────────────────────

class DashboardRoot(QWidget):
    """
    High-end backdrop for the official application.
    Supports subtle image backdrop with mesh-glow gradients for depth.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DashboardRoot")
        self._bg_pixmap = None
        
        # Load background if available
        assets_dir = os.path.join(PROJECT_ROOT, "Jarvis", "assets")
        img_path = os.path.join(assets_dir, "bg.png")
        if os.path.isfile(img_path):
            from PyQt6.QtGui import QPixmap
            self._bg_pixmap = QPixmap(img_path)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()

        if self._bg_pixmap and not self._bg_pixmap.isNull():
            # Scale and center (cover)
            pm_size = self._bg_pixmap.size()
            x_ratio = rect.width() / pm_size.width()
            y_ratio = rect.height() / pm_size.height()
            scale = max(x_ratio, y_ratio)
            
            scaled_w = int(pm_size.width() * scale)
            scaled_h = int(pm_size.height() * scale)
            x_off = (rect.width() - scaled_w) // 2
            y_off = (rect.height() - scaled_h) // 2
            p.drawPixmap(x_off, y_off, scaled_w, scaled_h, self._bg_pixmap)
            
            # Darkening overlay for professional readability
            p.fillRect(rect, QColor(2, 6, 23, 180)) # Dark slate overlay
        else:
            # Sophisticated base gradient
            grad = QLinearGradient(0, 0, rect.width(), rect.height())
            grad.setColorAt(0, QColor("#020617"))
            grad.setColorAt(1, QColor("#0f172a"))
            p.fillRect(rect, grad)

        # ── Mesh Glow Effects ──
        # Top-right indigo glow
        tr_glow = QRadialGradient(rect.width() * 0.8, rect.height() * 0.1, rect.width() * 0.4)
        tr_glow.setColorAt(0, QColor(99, 102, 241, 40)) # Indigo glow
        tr_glow.setColorAt(1, Qt.GlobalColor.transparent)
        p.fillRect(rect, tr_glow)
        
        # Bottom-left cyan glow
        bl_glow = QRadialGradient(rect.width() * 0.1, rect.height() * 0.9, rect.width() * 0.5)
        bl_glow.setColorAt(0, QColor(14, 165, 233, 30)) # Sky/Cyan glow
        bl_glow.setColorAt(1, Qt.GlobalColor.transparent)
        p.fillRect(rect, bl_glow)

        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  Professional UI Components
# ═══════════════════════════════════════════════════════════════════════════════

class DashboardSection(QFrame):
    """A professional container for dashboard segments with subtle depth."""
    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: rgba(11, 17, 32, 0.7); /* Semi-translucent for depth */
                border: 1px solid {dt.BORDER_DEFAULT};
                border-top: 1px solid rgba(255, 255, 255, 0.1); /* Subtle highlight */
                border-radius: {dt.RADIUS}px;
            }}
        """)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(dt.SPACING_LG, dt.SPACING_LG, dt.SPACING_LG, dt.SPACING_LG)
        self.layout.setSpacing(dt.SPACING_MD)

        if title:
            header = QLabel(title.upper())
            header.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_CAPTION, QFont.Weight.Black))
            header.setStyleSheet(f"color: {dt.TEXT_MUTED}; letter-spacing: 1.5px; border: none; background: transparent;")
            self.layout.addWidget(header)

    def add_widget(self, widget):
        self.layout.addWidget(widget)

    def add_layout(self, layout):
        self.layout.addLayout(layout)


class StatusBadge(QLabel):
    """A semantic status indicator."""
    def __init__(self, text, type="success", parent=None):
        super().__init__(f"  ●  {text.upper()}  ", parent)
        color = dt.SUCCESS if type == "success" else dt.INFO if type == "info" else dt.WARNING
        bg = dt.SUCCESS_BG if type == "success" else "rgba(14, 165, 233, 0.1)" if type == "info" else dt.WARNING_BG
        
        self.setStyleSheet(f"""
            background: {bg}; color: {color};
            border-radius: 4px; font-size: 8pt;
            font-weight: 800; padding: 4px 0px;
            border: 1px solid {color}33;
        """)

class MetricWidget(QWidget):
    """Simplified metric display with spark-like feel."""
    def __init__(self, label, value, unit="", parent=None):
        super().__init__(parent)
        l = QVBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(4)

        self.lbl = QLabel(label)
        self.lbl.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; font-size: 9pt; font-weight: 600;")
        
        self.val = QLabel(f"<span style='font-size: 18pt; font-weight: 900; color: {dt.TEXT_PRIMARY};'>{value}</span>"
                          f"<span style='font-size: 10pt; color: {dt.TEXT_MUTED}; font-weight: 400;'> {unit}</span>")
        
        l.addWidget(self.lbl)
        l.addWidget(self.val)


class SidebarButton(QPushButton):
    def __init__(self, text, icon_char=""):
        display_text = f"  {icon_char}   {text}" if icon_char else f"    {text}"
        super().__init__(display_text)
        self.setCheckable(True)
        self.setFixedHeight(40)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_BODY))
        self.setStyleSheet(f"""
            QPushButton {{
                color: {dt.TEXT_SECONDARY}; background: transparent;
                border: none; border-radius: {dt.RADIUS_SM}px;
                text-align: left; padding-left: 12px;
            }}
            QPushButton:hover {{
                color: {dt.TEXT_PRIMARY}; background: {dt.SIDEBAR_HOVER};
            }}
            QPushButton:checked {{
                color: {dt.ACCENT}; background: {dt.ACCENT_BG}; 
                font-weight: 700;
            }}
        """)


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Dashboard
# ═══════════════════════════════════════════════════════════════════════════════

class JarvisDashboard(QMainWindow):
    """Primary Jarvis Windows App — Official Application Dashboard."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis AI")
        self.resize(1100, 780)
        self.setMinimumSize(960, 640)
        
        # We'll use a standard window with custom styling for an 'official' feel
        # instead of a frameless glassmorphic window which can feel 'jargon'
        self.setStyleSheet(f"background-color: {dt.BG_BASE}; color: {dt.TEXT_PRIMARY};")
        
        self._build_ui()

    def _build_ui(self):
        # ── Root Backdrop ──
        self.root = DashboardRoot()
        self.setCentralWidget(self.root)
        
        main_layout = QHBoxLayout(self.root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Sidebar ──
        main_layout.addWidget(self._build_sidebar())

        # ── Content Area ──
        content_container = QWidget()
        clayout = QVBoxLayout(content_container)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(0)

        # Header / Title Bar
        header = self._build_header()
        clayout.addWidget(header)

        # Pages
        self.stack = QStackedWidget()
        self.pages = {}
        for name, builder in [
            ("Home",       self._build_home),
            ("Intelligence", self._build_models),
            ("Local Forge", self._build_local_llms),
            ("Security",    self._build_api_keys),
            ("Logs",       self._build_history),
        ]:
            page = builder()
            self.stack.addWidget(page)
            self.pages[name] = page

        clayout.addWidget(self.stack)
        main_layout.addWidget(content_container)

        # Default Page
        self._switch_page(0, self.nav_buttons["Home"])

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setFixedWidth(dt.SIDEBAR_WIDTH)
        sidebar.setStyleSheet(f"background: {dt.SIDEBAR_BG}; border-right: 1px solid {dt.BORDER_DEFAULT};")
        
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(4)

        # Branding
        brand = QLabel("JARVIS CORE")
        brand.setFont(QFont(dt.FONT_FAMILY, 12, QFont.Weight.Black))
        brand.setStyleSheet(f"color: {dt.ACCENT}; letter-spacing: 2px; margin-bottom: 30px; padding-left: 10px;")
        layout.addWidget(brand)

        self.nav_buttons = {}
        nav_items = [
            ("Home", "󰋜"), 
            ("Intelligence", "󰙨"), 
            ("Local Forge", "󰚗"), 
            ("Security", "󰌆"), 
            ("Logs", "󰄉")
        ]
        
        for i, (name, icon) in enumerate(nav_items):
            btn = SidebarButton(name, icon)
            btn.clicked.connect(lambda checked, idx=i, b=btn: self._switch_page(idx, b))
            layout.addWidget(btn)
            self.nav_buttons[name] = btn

        layout.addStretch()

        # Version info
        vinfo = QLabel("v2.5.0-STABLE")
        vinfo.setStyleSheet(f"color: {dt.TEXT_MUTED}; font-size: 8pt; font-family: '{dt.FONT_FAMILY_MONO}';")
        vinfo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(vinfo)

        return sidebar

    def _build_header(self):
        header = QFrame()
        header.setFixedHeight(dt.HEADER_HEIGHT)
        header.setStyleSheet(f"background: {dt.BG_BASE}; border-bottom: 1px solid {dt.BORDER_DEFAULT};")
        
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(24, 0, 24, 0)

        self.page_title = QLabel("Overview")
        self.page_title.setFont(QFont(dt.FONT_FAMILY, 14, QFont.Weight.Bold))
        hlayout.addWidget(self.page_title)

        hlayout.addStretch()

        # Status badge in header
        self.global_status = StatusBadge("System Nominal", "success")
        hlayout.addWidget(self.global_status)

        hlayout.addSpacing(20)

        launch_btn = QPushButton("Launch Assistant")
        launch_btn.setFixedSize(140, 32)
        launch_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        launch_btn.setStyleSheet(dt.button_primary_style())
        launch_btn.clicked.connect(self._launch_assistant)
        hlayout.addWidget(launch_btn)

        return header

    def _switch_page(self, index, btn):
        for b in self.nav_buttons.values():
            b.setChecked(False)
        btn.setChecked(True)
        self.stack.setCurrentIndex(index)
        self.page_title.setText(btn.text().strip().split(' ')[-1])

    def _launch_assistant(self):
        python_exe = sys.executable
        script_path = os.path.join(PROJECT_ROOT, "Jarvis", "main.py")
        subprocess.Popen(
            [python_exe, script_path, "--assistant"],
            cwd=PROJECT_ROOT,
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: Home (Overview)
    # ══════════════════════════════════════════════════════════════════════════

    def _build_home(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(dt.scrollarea_style())

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        # ── TOP ROW: SYSTEM SUMMARY ──
        top_row = QHBoxLayout()
        top_row.setSpacing(24)

        # Active Model Section
        model_sec = DashboardSection("Active Intelligence")
        model_sec.setFixedWidth(400)
        
        m_layout = QVBoxLayout()
        m_name = QLabel(_active_model_name())
        m_name.setFont(QFont(dt.FONT_FAMILY, 20, QFont.Weight.Black))
        m_name.setStyleSheet(f"color: {dt.ACCENT};")
        
        m_provider = QLabel(f"Provider: {LLM_PROVIDER.upper()}")
        m_provider.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; font-weight: 600;")
        
        m_layout.addWidget(m_name)
        m_layout.addWidget(m_provider)
        model_sec.add_layout(m_layout)
        top_row.addWidget(model_sec)

        # Performance Metrics
        perf_sec = DashboardSection("Real-time Health")
        p_layout = QHBoxLayout()
        p_layout.addWidget(MetricWidget("CPU USAGE", "12", "%"))
        p_layout.addWidget(MetricWidget("LATENCY", "18", "ms"))
        p_layout.addWidget(MetricWidget("MEMORY", "1.2", "GB"))
        perf_sec.add_layout(p_layout)
        top_row.addWidget(perf_sec)

        layout.addLayout(top_row)

        # ── MIDDLE ROW: TOOLS & CAPABILITIES ──
        tools_label = QLabel("QUICK ACCESS TOOLS")
        tools_label.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_CAPTION, QFont.Weight.Black))
        tools_label.setStyleSheet(f"color: {dt.TEXT_MUTED}; letter-spacing: 1.5px;")
        layout.addWidget(tools_label)

        tools_grid = QGridLayout()
        tools_grid.setSpacing(16)
        
        tool_items = [
            ("󰏘", "Creative Mode", "High-fidelity vision and image synthesis.", "#D946EF"),
            ("󰅩", "Coding Forge", "Autonomous development and refactoring.", "#3B82F6"),
            ("󰖟", "Knowledge Base", "Deep web search and retrieval augmented generation.", "#06B6D4"),
            ("󰙨", "Model Tuning", "Fine-tune and optimize local weight parameters.", "#10B981")
        ]

        for i, (icon, name, desc, color) in enumerate(tool_items):
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {dt.BG_SURFACE};
                    border: 1px solid {dt.BORDER_DEFAULT};
                    border-radius: {dt.RADIUS}px;
                }}
                QFrame:hover {{
                    border-color: {color};
                    background: {dt.BG_SURFACE_ALT};
                }}
            """)
            card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            card.mousePressEvent = lambda e, n=name: self._handle_quick_tool(n)
            
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 16, 16, 16)

            ic = QLabel(icon)
            ic.setFont(QFont(dt.FONT_FAMILY, 20))
            ic.setStyleSheet(f"color: {color}; border: none; background: transparent;")
            cl.addWidget(ic)

            nl = QLabel(name)
            nl.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H3, QFont.Weight.Bold))
            cl.addWidget(nl)

            dl = QLabel(desc)
            dl.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; font-size: 8pt;")
            dl.setWordWrap(True)
            cl.addWidget(dl)
            
            tools_grid.addWidget(card, i // 2, i % 2)

        layout.addLayout(tools_grid)

        # ── BOTTOM ROW: RECENT ACTIVITY ──
        activity_sec = DashboardSection("Recent System Logs")
        
        for time, tag, text in [
            ("16:02", "SYSTEM", "Jarvis initialized — all systems nominal"),
            ("16:01", "MODEL",  f"Loaded {_active_model_name()} on {LLM_PROVIDER}"),
            ("15:58", "USER",   "Analyze current codebase for performance bottlenecks"),
        ]:
            row = QHBoxLayout()
            row.setContentsMargins(0, 4, 0, 4)
            
            ts = QLabel(time)
            ts.setFixedWidth(50)
            ts.setStyleSheet(f"color: {dt.TEXT_MUTED}; font-family: '{dt.FONT_FAMILY_MONO}'; font-size: 8pt;")
            
            tg = StatusBadge(tag, "info" if tag == "SYSTEM" else "success")
            
            msg = QLabel(text)
            msg.setStyleSheet(f"color: {dt.TEXT_PRIMARY}; font-size: 9pt;")
            
            row.addWidget(ts)
            row.addWidget(tg)
            row.addWidget(msg)
            row.addStretch()
            activity_sec.add_layout(row)
            
        layout.addWidget(activity_sec)
        layout.addStretch()

        page.setWidget(content)
        return page

    # ── Tool Handlers ────────────────────────────────────────────────────────

    def _handle_quick_tool(self, name):
        if name == "Creative Mode":
            self._do_image_gen()
        elif name == "Coding Forge":
            self._do_code_assistant()
        elif name == "Knowledge Base":
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
        models = ["gemini-2.0-flash", "llama-3.3-70b-versatile", "gpt-4o"]
        model, ok = QInputDialog.getItem(self, "Coding Forge", "Select specialized model:", models, 0, False)
        if ok and model:
            os.environ["GEMINI_MODEL"] = model
            self._launch_assistant()

    def _do_web_search(self):
        from PyQt6.QtWidgets import QInputDialog, QMessageBox
        from Jarvis.core.web_search import web_search
        
        query, ok = QInputDialog.getText(self, "Knowledge Base", "Enter search query:")
        if ok and query:
            msg = QMessageBox(self)
            msg.setWindowTitle("Searching...")
            msg.setText("Searching the web...")
            msg.setStandardButtons(QMessageBox.StandardButton.NoButton)
            msg.show()
            QApplication.processEvents()
            
            resp = web_search(query, max_results=5)
            msg.accept()
            
            if resp.results:
                text = f"<h3>Results for: {query}</h3>"
                for r in resp.results:
                    text += f"<b>{r.title}</b><br>{r.snippet}<br><br>"
                res_box = QMessageBox(self)
                res_box.setText(text)
                res_box.exec()

    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: Intelligence (Models)
    # ══════════════════════════════════════════════════════════════════════════

    def _build_models(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(dt.scrollarea_style())

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        lay.addWidget(QLabel("CLOUD PROVIDER STATUS"))

        for name, models, active in [
            ("OpenAI", ["GPT-4o", "GPT-3.5-Turbo"], False),
            ("Google Gemini", [GEMINI_MODEL], LLM_PROVIDER == "gemini"),
            ("Groq", [GROQ_MODEL], LLM_PROVIDER == "groq"),
            ("Anthropic", ["Claude 3.5 Sonnet"], False),
        ]:
            sec = DashboardSection()
            sl = QHBoxLayout()
            
            info = QVBoxLayout()
            n = QLabel(name)
            n.setFont(QFont(dt.FONT_FAMILY, 12, QFont.Weight.Bold))
            info.addWidget(n)
            
            m = QLabel(", ".join(models))
            m.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; font-size: 9pt;")
            info.addWidget(m)
            
            sl.addLayout(info)
            sl.addStretch()
            
            if active:
                sl.addWidget(StatusBadge("CONNECTED", "success"))
            else:
                btn = QPushButton("Connect")
                btn.setFixedSize(80, 28)
                btn.setStyleSheet(dt.button_secondary_style())
                sl.addWidget(btn)
                
            sec.add_layout(sl)
            lay.addWidget(sec)

        lay.addStretch()
        page.setWidget(content)
        return page

    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: Local Forge
    # ══════════════════════════════════════════════════════════════════════════

    def _build_local_llms(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(dt.scrollarea_style())

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        lay.addWidget(QLabel("LOCAL HARDWARE ACCELERATION"))
        
        hardware = DashboardSection()
        hw_layout = QHBoxLayout()
        hw_layout.addWidget(MetricWidget("VRAM", "10.4 / 16", "GB"))
        hw_layout.addWidget(MetricWidget("GPU LOAD", "45", "%"))
        hw_layout.addWidget(MetricWidget("TEMP", "62", "°C"))
        hardware.add_layout(hw_layout)
        lay.addWidget(hardware)

        lay.addWidget(QLabel("AVAILABLE LOCAL SPECIMENS"))
        
        for name, params in [("Llama 3 (8B)", "8.0B"), ("Mistral Large", "8.0B"), ("Gemma 7B", "7.0B")]:
            sec = DashboardSection()
            sl = QHBoxLayout()
            sl.addWidget(QLabel(name))
            sl.addStretch()
            sl.addWidget(QLabel(f"Params: {params}"))
            sl.addSpacing(20)
            btn = QPushButton("LOAD")
            btn.setFixedSize(60, 28)
            btn.setStyleSheet(dt.button_secondary_style())
            sl.addWidget(btn)
            sec.add_layout(sl)
            lay.addWidget(sec)

        lay.addStretch()
        page.setWidget(content)
        return page

    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: Security (API Keys)
    # ══════════════════════════════════════════════════════════════════════════

    def _build_api_keys(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(dt.scrollarea_style())

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        lay.addWidget(QLabel("CREDENTIAL MANAGEMENT"))

        for label, val in [("GEMINI_API_KEY", GEMINI_API_KEY), ("GROQ_API_KEY", GROQ_API_KEY)]:
            sec = DashboardSection()
            sl = QHBoxLayout()
            sl.addWidget(QLabel(label))
            sl.addStretch()
            
            inp = QLineEdit()
            inp.setFixedWidth(240)
            inp.setEchoMode(QLineEdit.EchoMode.Password)
            inp.setText(val)
            inp.setStyleSheet(dt.input_style())
            sl.addWidget(inp)
            
            sec.add_layout(sl)
            lay.addWidget(sec)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save = QPushButton("Apply Credentials")
        save.setFixedSize(140, 32)
        save.setStyleSheet(dt.button_primary_style())
        btn_row.addWidget(save)
        lay.addLayout(btn_row)

        lay.addStretch()
        page.setWidget(content)
        return page

    # ══════════════════════════════════════════════════════════════════════════
    #  PAGE: Logs (History)
    # ══════════════════════════════════════════════════════════════════════════

    def _build_history(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(dt.scrollarea_style())

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(8)

        lay.addWidget(QLabel("INTERACTION LEDGER"))

        for time, tag, text in [
            ("16:02", "SYSTEM", "Jarvis initialized — all systems nominal"),
            ("16:01", "MODEL",  f"Loaded {_active_model_name()} on {LLM_PROVIDER}"),
            ("15:58", "USER",   "Analyze current codebase for performance bottlenecks"),
            ("15:55", "ACTION", "Executed: spotify play Lo-fi Beats"),
            ("15:50", "USER",   "What's the weather today?"),
        ]:
            sec = DashboardSection()
            sec.layout.setContentsMargins(12, 8, 12, 8)
            row = QHBoxLayout()
            row.addWidget(QLabel(time))
            row.addWidget(StatusBadge(tag, "info"))
            row.addWidget(QLabel(text))
            row.addStretch()
            sec.add_layout(row)
            lay.addWidget(sec)

        lay.addStretch()
        page.setWidget(content)
        return page

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = JarvisDashboard()
    window.show()
    sys.exit(app.exec())
