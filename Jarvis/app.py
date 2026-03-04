"""
Jarvis Dashboard — Standalone Entry Point
==========================================
Launches the glassmorphic dashboard UI without any microphone,
listener, or TTS dependencies.  The voice assistant can be
started from inside the dashboard via "Launch Assistant".

Usage:
    python -m Jarvis.app
"""
import sys
import os

# Add parent directory to sys.path (before any Jarvis imports)
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase
from Jarvis.ui.dashboard import JarvisDashboard


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    # Load Inter font if bundled, otherwise fall back to system
    inter_path = os.path.join(current_dir, "assets", "Inter.ttf")
    if os.path.isfile(inter_path):
        QFontDatabase.addApplicationFont(inter_path)

    # Initialize database for profile/preferences/memories tabs
    try:
        from Jarvis.core.database import get_database
        get_database()
        from Jarvis.core.user_profile import get_profile_manager
        get_profile_manager().get_or_create_default_user()
    except Exception as e:
        print(f"[Warn] Database init failed (non-fatal): {e}")

    dashboard = JarvisDashboard()
    dashboard.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
