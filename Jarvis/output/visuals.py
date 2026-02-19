
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QBrush, QColor, QConicalGradient
from PyQt6.QtCore import Qt, QTimer, QPoint

class ThinkingOrb(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(100, 100)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_orb)
        self.timer.start(50)  # Update every 50ms
        self.angle = 0

    def update_orb(self):
        self.angle += 5
        if self.angle >= 360:
            self.angle = 0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Center point
        center = self.rect().center()
        
        # Draw base orb
        radius = min(self.width(), self.height()) / 2 - 10
        if radius < 0: radius = 10 
        
        gradient = QConicalGradient(center.x(), center.y(), self.angle)
        gradient.setColorAt(0, QColor(0, 255, 255))
        gradient.setColorAt(0.5, QColor(0, 0, 255))
        gradient.setColorAt(1, QColor(0, 255, 255))
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, int(radius), int(radius))
