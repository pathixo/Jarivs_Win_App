import os
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QStackedWidget, QPushButton, QLabel, QFrame, 
                             QScrollArea, QGridLayout, QProgressBar, QCheckBox, 
                             QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QIcon, QCursor, QColor

from Jarvis.ui import design_tokens as dt
from Jarvis.config import (LLM_PROVIDER, OLLAMA_MODEL, GEMINI_MODEL, GROQ_MODEL, 
                           STT_PROVIDER, TTS_ENGINE, PIPELINE_MODE, BARGE_IN_ENABLED, 
                           VAD_ENGINE, RESPONSE_STYLE, DEFAULT_PERSONA, TTS_VOICE)

class SidebarButton(QPushButton):
    """Custom sidebar navigation button."""
    def __init__(self, text, icon_name=None):
        super().__init__(text)
        self.setCheckable(True)
        self.setFixedHeight(40)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        # Styles applied in QSS via setStyleSheet in parent
        self.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_BODY))
        self.setStyleSheet(f"""
            QPushButton {{
                color: {dt.TEXT_SECONDARY};
                background: transparent;
                border: none;
                border-radius: {dt.RADIUS_SM}px;
                text-align: left;
                padding-left: {dt.SPACING_MD}px;
            }}
            QPushButton:hover {{
                color: {dt.TEXT_PRIMARY};
                background: {dt.SIDEBAR_HOVER};
            }}
            QPushButton:checked {{
                color: {dt.TEXT_ON_ACCENT};
                background: {dt.SIDEBAR_ACTIVE};
                border-left: 3px solid {dt.SIDEBAR_INDICATOR};
                border-top-left-radius: 0;
                border-bottom-left-radius: 0;
                font-weight: bold;
            }}
        """)


class SettingsWindow(QMainWindow):
    """Main Settings Window matching Stitch UI design."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis Settings")
        self.resize(1100, 780)
        self.setMinimumSize(960, 640)
        
        # Standard window for official application feel
        self.setStyleSheet(f"background-color: {dt.BG_BASE}; color: {dt.TEXT_PRIMARY};")

        self._init_ui()

    def _init_ui(self):
        # ── Main Container ──
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Body (Sidebar + Stacked Widget) ──
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(dt.SIDEBAR_WIDTH)
        self.sidebar.setStyleSheet(f"""
            QFrame {{
                background: {dt.SIDEBAR_BG};
                border-right: 1px solid {dt.BORDER_DEFAULT};
            }}
        """)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 24, 16, 24)
        sidebar_layout.setSpacing(4)
        
        # Branding in Settings
        brand = QLabel("SETTINGS")
        brand.setFont(QFont(dt.FONT_FAMILY, 10, QFont.Weight.Black))
        brand.setStyleSheet(f"color: {dt.TEXT_MUTED}; letter-spacing: 2px; margin-bottom: 20px; padding-left: 10px;")
        sidebar_layout.addWidget(brand)

        # Content Stack
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background: {dt.BG_BASE};")

        # Pages
        self.pages = {}
        self.nav_buttons = {}

        nav_items = [
            ("Overview", self._build_home_page()),
            ("Security", self._build_api_page()),
            ("Models", self._build_models_page()),
            ("System", self._build_settings_page()),
            ("Logs", self._build_history_page())
        ]

        for i, (name, widget) in enumerate(nav_items):
            # Nav Button
            btn = SidebarButton(name)
            btn.clicked.connect(lambda checked, idx=i, b=btn: self._switch_page(idx, b))
            sidebar_layout.addWidget(btn)
            self.nav_buttons[name] = btn
            
            # Stack Page
            self.stack.addWidget(widget)
            self.pages[name] = widget

        sidebar_layout.addStretch()
        
        # Version Label
        version_label = QLabel("v2.5.0-STABLE")
        version_label.setStyleSheet(f"color: {dt.TEXT_MUTED}; font-size: 8pt; font-family: '{dt.FONT_FAMILY_MONO}';")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(version_label)

        body_layout.addWidget(self.sidebar)
        body_layout.addWidget(self.stack)

        main_layout.addWidget(body_widget)

        # Default page
        if "Overview" in self.nav_buttons:
            self._switch_page(0, self.nav_buttons["Overview"])

    def _switch_page(self, index, active_btn):
        for btn in self.nav_buttons.values():
            btn.setChecked(False)
        active_btn.setChecked(True)
        self.stack.setCurrentIndex(index)

    # ── Page Builders ──

    def _build_page_container(self, title, subtitle=None):
        """Helper to create standard page structure."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(dt.SPACING_XL, dt.SPACING_XL, dt.SPACING_XL, dt.SPACING_XL)
        layout.setSpacing(dt.SPACING_LG)

        header = QLabel(title)
        header.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H1, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {dt.TEXT_PRIMARY};")
        layout.addWidget(header)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_BODY))
            sub.setStyleSheet(f"color: {dt.TEXT_SECONDARY};")
            layout.addWidget(sub)

        return page, layout

    def _build_home_page(self):
        page, layout = self._build_page_container("AI Assistant Home Dashboard", "Overview of Jarvis operations and status.")
        
        # Stats Cards Grid
        grid = QGridLayout()
        grid.setSpacing(dt.SPACING_LG)

        stats = [
            ("Status", "● Online", dt.SUCCESS),
            ("Active Brain", LLM_PROVIDER.upper(), dt.ACCENT),
            ("Active Model", GEMINI_MODEL if LLM_PROVIDER=="gemini" else GROQ_MODEL, dt.TEXT_PRIMARY),
            ("Pipeline Mode", PIPELINE_MODE.title(), dt.TEXT_PRIMARY)
        ]

        for i, (title, val, color) in enumerate(stats):
            card = QFrame()
            card.setStyleSheet(dt.card_style())
            card_layout = QVBoxLayout(card)
            
            t_lbl = QLabel(title)
            t_lbl.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; font-size: {dt.FONT_SIZE_SMALL}pt;")
            
            v_lbl = QLabel(val)
            v_lbl.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H2, QFont.Weight.Bold))
            v_lbl.setStyleSheet(f"color: {color}; border: none;")
            
            card_layout.addWidget(t_lbl)
            card_layout.addWidget(v_lbl)
            grid.addWidget(card, i // 2, i % 2)

        layout.addLayout(grid)
        layout.addStretch()
        return page

    def _build_api_page(self):
        page, layout = self._build_page_container("API & Model Management", "Configure active AI providers and API keys.")
        
        # Scroll Area for Providers
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(dt.scrollarea_style())
        
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(dt.SPACING_LG)
        content_layout.setContentsMargins(0, 0, dt.SPACING_MD, 0)
        
        providers = [
            ("OpenAI", ["GPT-4o", "GPT-3.5-Turbo"], 75),
            ("Anthropic", ["Claude 3.5 Sonnet", "Opus"], 25),
            ("Groq", ["Llama-3.3-70b-versatile", "Mixtral 8x7b"], 10),
            ("Google Gemini", [GEMINI_MODEL, "gemini-1.5-pro"], 50)
        ]

        for name, models, usage in providers:
            card = QFrame()
            card.setStyleSheet(dt.card_style() + f"QFrame {{ background: {dt.BG_SURFACE}; }}")
            c_layout = QVBoxLayout(card)
            
            header = QHBoxLayout()
            h_lbl = QLabel(name)
            h_lbl.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H3, QFont.Weight.Bold))
            header.addWidget(h_lbl)
            
            # Active badge
            if name.split(' ')[-1].lower() == LLM_PROVIDER.lower():
                badge = QLabel("ACTIVE")
                badge.setStyleSheet(f"background: {dt.SUCCESS_BG}; color: {dt.SUCCESS}; padding: 2px 6px; border-radius: {dt.RADIUS_SM}px; font-size: {dt.FONT_SIZE_CAPTION}pt; font-weight: bold;")
                header.addWidget(badge)
            
            header.addStretch()
            c_layout.addLayout(header)
            
            # Models
            m_lbl = QLabel(", ".join(models))
            m_lbl.setStyleSheet(f"color: {dt.TEXT_SECONDARY};")
            c_layout.addWidget(m_lbl)
            
            # Usage
            usage_bar = QProgressBar()
            usage_bar.setValue(usage)
            usage_bar.setTextVisible(False)
            usage_bar.setStyleSheet(dt.progress_bar_style(dt.ACCENT if usage < 80 else dt.ERROR))
            c_layout.addWidget(usage_bar)
            
            u_lbl = QLabel(f"{usage}% usage limit")
            u_lbl.setStyleSheet(f"color: {dt.TEXT_MUTED}; font-size: {dt.FONT_SIZE_SMALL}pt;")
            c_layout.addWidget(u_lbl)
            
            content_layout.addWidget(card)
            
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        return page

    def _build_models_page(self):
        page, layout = self._build_page_container("Local LLM Configuration Hub", "Manage local Ollama models for Voice AI processing.")
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(dt.scrollarea_style())
        
        content = QWidget()
        c_layout = QVBoxLayout(content)
        
        lbl = QLabel("Hardware Monitoring")
        lbl.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H2, QFont.Weight.Bold))
        c_layout.addWidget(lbl)
        
        # HW Grid
        hw_grid = QGridLayout()
        cpu_card = QFrame()
        cpu_card.setStyleSheet(dt.card_style())
        cpu_l = QVBoxLayout(cpu_card)
        cpu_l.addWidget(QLabel("CPU Usage"))
        cpu_bar = QProgressBar()
        cpu_bar.setValue(32)
        cpu_bar.setTextVisible(False)
        cpu_bar.setStyleSheet(dt.progress_bar_style(dt.SUCCESS))
        cpu_l.addWidget(cpu_bar)
        hw_grid.addWidget(cpu_card, 0, 0)
        
        gpu_card = QFrame()
        gpu_card.setStyleSheet(dt.card_style())
        gpu_l = QVBoxLayout(gpu_card)
        gpu_l.addWidget(QLabel("GPU VRAM Usage (6.4 / 8.0 GB)"))
        gpu_bar = QProgressBar()
        gpu_bar.setValue(80)
        gpu_bar.setTextVisible(False)
        gpu_bar.setStyleSheet(dt.progress_bar_style(dt.WARNING))
        gpu_l.addWidget(gpu_bar)
        hw_grid.addWidget(gpu_card, 0, 1)
        
        c_layout.addLayout(hw_grid)
        
        # Loaded Models
        lbl2 = QLabel("Loaded Models")
        lbl2.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_H2, QFont.Weight.Bold))
        lbl2.setStyleSheet(f"margin-top: {dt.SPACING_LG}px;")
        c_layout.addWidget(lbl2)
        
        models = [
            ("Llama-3-8B-Instruct", "~5.5 GB VRAM", True),
            ("Mistral-7B-v0.2", "4.8 GB VRAM", False),
            (OLLAMA_MODEL, "Action Classifier", True)
        ]
        
        for name, req, loaded in models:
            card = QFrame()
            card.setStyleSheet(dt.card_style())
            cl = QHBoxLayout(card)
            cl.addWidget(QLabel(f"<b>{name}</b>"))
            cl.addStretch()
            cl.addWidget(QLabel(req))
            if loaded:
                bg = QLabel("LOADED")
                bg.setStyleSheet(f"background: {dt.ACCENT_BG}; color: {dt.ACCENT}; padding: 2px 6px; border-radius: {dt.RADIUS_SM}px;")
                cl.addWidget(bg)
            c_layout.addWidget(card)

        c_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        return page

    def _build_settings_page(self):
        page, layout = self._build_page_container("User Profile and Voice Settings", "Configure your local persona and pipeline behaviour.")
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(dt.scrollarea_style())
        
        content = QWidget()
        c_layout = QVBoxLayout(content)
        c_layout.setSpacing(dt.SPACING_LG)
        
        def _build_field(label, current_val, options=None):
            grp = QWidget()
            l = QVBoxLayout(grp)
            l.setContentsMargins(0, 0, 0, 0)
            l.setSpacing(dt.SPACING_SM)
            
            lbl = QLabel(label)
            lbl.setFont(QFont(dt.FONT_FAMILY, dt.FONT_SIZE_BODY, QFont.Weight.Bold))
            l.addWidget(lbl)
            
            if options:
                cb = QComboBox()
                cb.addItems(options)
                cb.setCurrentText(current_val)
                cb.setStyleSheet(dt.combobox_style())
                l.addWidget(cb)
            else:
                inp = QLabel(str(current_val))
                inp.setStyleSheet(f"color: {dt.TEXT_SECONDARY}; padding: {dt.SPACING_SM}px; background: {dt.BG_SURFACE}; border: 1px solid {dt.BORDER_DEFAULT}; border-radius: {dt.RADIUS_SM}px;")
                l.addWidget(inp)
                
            return grp

        # Forms
        card = QFrame()
        card.setStyleSheet(dt.card_style())
        f_layout = QVBoxLayout(card)
        f_layout.setSpacing(dt.SPACING_LG)
        
        f_layout.addWidget(_build_field("Persona", DEFAULT_PERSONA, ["jarvis", "samantha", "codex", "default"]))
        f_layout.addWidget(_build_field("Speech-to-Text Provider", STT_PROVIDER, ["auto", "groq", "local"]))
        f_layout.addWidget(_build_field("Text-to-Speech Engine", TTS_ENGINE, ["auto", "kokoro", "edge"]))
        f_layout.addWidget(_build_field("TTS Voice", TTS_VOICE))
        f_layout.addWidget(_build_field("Pipeline Mode", PIPELINE_MODE, ["streaming", "sequential"]))
        f_layout.addWidget(_build_field("Response Style", RESPONSE_STYLE, ["concise", "detailed"]))
        
        # Toggle
        chk = QCheckBox("Enable Barge-In (Interrupt Jarvis)")
        chk.setChecked(BARGE_IN_ENABLED)
        chk.setStyleSheet(dt.toggle_style())
        f_layout.addWidget(chk)
        
        c_layout.addWidget(card)
        
        # Save btn
        b_hl = QHBoxLayout()
        b_hl.addStretch()
        btn = QPushButton("Save Preferences")
        btn.setStyleSheet(dt.button_primary_style())
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        b_hl.addWidget(btn)
        c_layout.addLayout(b_hl)
        
        c_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        return page

    def _build_history_page(self):
        page, layout = self._build_page_container("Interaction History & Logs", "View recent conversational context.")
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(dt.scrollarea_style())
        
        content = QWidget()
        c_layout = QVBoxLayout(content)
        
        # Mock Logs matching Stitch design
        for log in ["System Initialized", "Loaded model gemini-2.0-flash", "Action: Play music via Spotify", "User: 'What's the weather today?'", "Jarvis: 'It is currently 22 degrees and sunny.'"]:
            card = QFrame()
            card.setStyleSheet(dt.card_style() + f"QFrame {{ padding: {dt.SPACING_MD}px; }}")
            cl = QHBoxLayout(card)
            cl.addWidget(QLabel(log))
            c_layout.addWidget(card)
            
        c_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        return page

    # ── Window Dragging ──
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < dt.HEADER_HEIGHT:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

