"""
Terminal & Telemetry Window Module
==================================
Official "Agent Telemetry & Thought Log" for Swara-Core.
Provides real-time visibility into the agent's processing pipeline, 
chain-of-thought reasoning, and tool execution.
"""

import sys
from datetime import datetime
from collections import deque
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QTextEdit, QLabel, QFrame, QApplication, QScrollArea)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QTextCursor, QTextCharFormat, QFontDatabase

from Jarvis.ui import design_tokens as dt
from Jarvis.core.terminal_bridge import get_terminal_bridge


class PipelineStep(QLabel):
    """A single visual step in the agent pipeline."""
    def __init__(self, text, parent=None):
        super().__init__(text.upper(), parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(24)
        self.setFixedWidth(100)
        self.setFont(QFont(dt.FONT_FAMILY, 7, QFont.Weight.Black))
        self.set_state("idle")

    def set_state(self, state):
        if state == "active":
            self.setStyleSheet(f"""
                background: {dt.ACCENT}; color: {dt.TEXT_ON_ACCENT};
                border-radius: 12px; border: 1px solid {dt.ACCENT_HOVER};
            """)
        elif state == "completed":
            self.setStyleSheet(f"""
                background: {dt.SUCCESS_BG}; color: {dt.SUCCESS};
                border-radius: 12px; border: 1px solid {dt.SUCCESS}33;
            """)
        else: # idle
            self.setStyleSheet(f"""
                background: transparent; color: {dt.TEXT_MUTED};
                border-radius: 12px; border: 1px solid {dt.BORDER_DEFAULT};
            """)


class TerminalWindow(QMainWindow):
    """
    Industry-grade Telemetry & Thought Log.
    Provides deep transparency into Agent operations.
    """
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis Telemetry & Thought Log")
        self.resize(1100, 750)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.central_widget.setStyleSheet(f"background: {dt.BG_BASE};")
        
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ─── 1. Header & Pipeline Tracker ─────────────────────────────────────
        self.header = QFrame()
        self.header.setFixedHeight(80)
        self.header.setStyleSheet(f"background: {dt.BG_SURFACE}; border-bottom: 1px solid {dt.BORDER_DEFAULT};")
        header_layout = QVBoxLayout(self.header)
        header_layout.setContentsMargins(20, 10, 20, 10)
        
        top_h = QHBoxLayout()
        title = QLabel("󰆍  AGENT TELEMETRY")
        title.setFont(QFont(dt.FONT_FAMILY, 10, QFont.Weight.Black))
        title.setStyleSheet(f"color: {dt.ACCENT}; letter-spacing: 2px;")
        top_h.addWidget(title)
        top_h.addStretch()
        
        self.status_label = QLabel("● SYSTEM READY")
        self.status_label.setFont(QFont(dt.FONT_FAMILY, 8, QFont.Weight.Bold))
        self.status_label.setStyleSheet(f"color: {dt.SUCCESS};")
        top_h.addWidget(self.status_label)
        header_layout.addLayout(top_h)
        
        # Pipeline visualizer
        self.pipeline_layout = QHBoxLayout()
        self.pipeline_layout.setSpacing(8)
        self.steps = {
            "LISTENING":    PipelineStep("Listening"),
            "TRANSCRIBING": PipelineStep("Transcribing"),
            "ROUTING":      PipelineStep("Routing"),
            "THINKING":     PipelineStep("Thinking"),
            "EXECUTING":    PipelineStep("Executing"),
            "SPEAKING":     PipelineStep("Speaking"),
        }
        for step in self.steps.values():
            self.pipeline_layout.addWidget(step)
        header_layout.addLayout(self.pipeline_layout)
        
        main_layout.addWidget(self.header)
        
        # ─── 2. Main Telemetry Log (The Feed) ─────────────────────────────────
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet(f"""
            QTextEdit {{
                background: {dt.BG_BASE};
                color: {dt.TEXT_SECONDARY};
                border: none;
                padding: 24px;
                line-height: 1.5;
            }}
        """)
        self.log_display.setFont(QFont(dt.FONT_FAMILY_MONO, 10))
        main_layout.addWidget(self.log_display)
        
        # ─── 3. Footer Stats ──────────────────────────────────────────────────
        self.footer = QFrame()
        self.footer.setFixedHeight(32)
        self.footer.setStyleSheet(f"background: {dt.BG_SURFACE}; border-top: 1px solid {dt.BORDER_DEFAULT};")
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(20, 0, 20, 0)
        
        self.stats_label = QLabel("ENGINE: LOCAL (OLLAMA)  |  LLM: QWEN 2.5")
        self.stats_label.setFont(QFont(dt.FONT_FAMILY_MONO, 7))
        self.stats_label.setStyleSheet(f"color: {dt.TEXT_MUTED};")
        footer_layout.addWidget(self.stats_label)
        footer_layout.addStretch()
        
        self.latency_label = QLabel("LATENCY: 0ms")
        self.latency_label.setFont(QFont(dt.FONT_FAMILY_MONO, 7))
        self.latency_label.setStyleSheet(f"color: {dt.TEXT_MUTED};")
        footer_layout.addWidget(self.latency_label)
        
        main_layout.addWidget(self.footer)
        
        # Wire signals
        self.bridge = get_terminal_bridge()
        self.bridge.telemetry_event.connect(self.handle_telemetry_event)
        self.bridge.status_update.connect(self.update_status)
        
        self._init_display()

    def _init_display(self):
        self.log_display.clear()
        self._append_log("TELEMETRY", "Session Initialized. Awaiting command...", color=dt.TEXT_MUTED)
        self._append_log("SYSTEM", "Pipeline health check: NOMINAL", color=dt.SUCCESS)
        self._append_divider()

    def handle_telemetry_event(self, phase, message, event_type, provider, model, timestamp):
        """Slot for the industry-grade telemetry signal."""
        # 1. Update Pipeline Visuals
        self._update_pipeline_visuals(phase)
        
        # 2. Update Footer Stats if model/provider is sent
        if provider or model:
            self.stats_label.setText(f"PROVIDER: {provider.upper()} | MODEL: {model.upper()}")
        
        # 3. Format and Append Log
        time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S.%f")[:-3]
        color = self._get_color_for_type(event_type)
        
        self._append_log(phase, message, color, time_str, event_type)

    def _update_pipeline_visuals(self, active_phase):
        found_active = False
        for phase_name, step in self.steps.items():
            if phase_name == active_phase:
                step.set_state("active")
                found_active = True
            elif not found_active and active_phase != "IDLE":
                step.set_state("completed")
            else:
                step.set_state("idle")
        
        if active_phase == "IDLE":
            for step in self.steps.values(): step.set_state("idle")

    def _get_color_for_type(self, event_type):
        return {
            "SUCCESS": dt.SUCCESS,
            "WARNING": dt.WARNING,
            "ERROR":   dt.ERROR,
            "THOUGHT": "#A78BFA", # Soft Purple/Violet for CoT
            "TOOL":    "#38BDF8", # Sky Blue for Tool/Exec
            "INFO":    dt.TEXT_SECONDARY
        }.get(event_type, dt.TEXT_SECONDARY)

    def _append_log(self, phase, message, color, time_str=None, event_type=None):
        if not time_str:
            time_str = datetime.now().strftime("%H:%M:%S")
            
        cursor = self.log_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Timestamp
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(dt.TEXT_MUTED))
        cursor.setCharFormat(fmt)
        cursor.insertText(f"[{time_str}] ")
        
        # Phase Tag
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        fmt.setFontWeight(QFont.Weight.Bold)
        cursor.setCharFormat(fmt)
        cursor.insertText(f"{phase.ljust(12)} ")
        
        # Icon based on type
        icon = {
            "SUCCESS": "✓ ", "ERROR": "✗ ", "WARNING": "⚠ ", 
            "THOUGHT": "🧠 ", "TOOL": "⚙ ", "INFO": "• "
        }.get(event_type, "• ")
        cursor.insertText(icon)
        
        # Message
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(dt.TEXT_PRIMARY if event_type in ["THOUGHT", "TOOL"] else color))
        fmt.setFontWeight(QFont.Weight.Normal)
        cursor.setCharFormat(fmt)
        
        # Indent multi-line messages
        lines = message.split('\n')
        cursor.insertText(lines[0] + "\n")
        if len(lines) > 1:
            for line in lines[1:]:
                cursor.insertText(" " * 24 + line + "\n")
        
        self.log_display.setTextCursor(cursor)
        self.log_display.ensureCursorVisible()

    def _append_divider(self):
        cursor = self.log_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(dt.BORDER_DEFAULT))
        cursor.setCharFormat(fmt)
        cursor.insertText("─" * 80 + "\n")
        self.log_display.setTextCursor(cursor)

    def update_status(self, text, status_type):
        color = dt.SUCCESS if status_type == "listening" else dt.ACCENT if status_type == "processing" else dt.ERROR
        self.status_label.setText(f"● {text.upper()}")
        self.status_label.setStyleSheet(f"color: {color};")

    def closeEvent(self, event):
        event.ignore()
        self.hide()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TerminalWindow()
    window.show()
    sys.exit(app.exec())
