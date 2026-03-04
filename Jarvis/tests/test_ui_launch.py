
import sys
import os
import unittest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Add project root to sys.path explicitly
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print(f"Project Root added to path: {project_root}")
from Jarvis.ui.window import MainWindow
from Jarvis.ui.settings_window import SettingsWindow

class TestUILaunch(unittest.TestCase):
    def test_launch_window(self):
        """
        Test that the main window launches without error and closes after a short delay.
        """
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)
        window = MainWindow()
        window.show()
        
        self.assertTrue(window.isVisible())
        self.assertEqual(window.windowTitle(), "Jarvis AI")
        
        # Close the window after 1 second to finish the test
        QTimer.singleShot(1000, app.quit)
        
        # Run the event loop
        app.exec()

    def test_launch_settings_window(self):
        """
        Test that the new settings window launches and can navigate tabs.
        """
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)
        
        settings = SettingsWindow()
        settings.show()
        
        self.assertTrue(settings.isVisible())
        self.assertEqual(settings.windowTitle(), "Jarvis Settings")
        
        # Check nav buttons created
        self.assertIn("Home", settings.nav_buttons)
        self.assertIn("Settings", settings.nav_buttons)
        
        # Test tab switching
        settings.nav_buttons["Settings"].click()
        self.assertEqual(settings.stack.currentWidget(), settings.pages["Settings"])

        # Close the window after a short delay
        QTimer.singleShot(1000, app.quit)
        app.exec()

if __name__ == '__main__':
    unittest.main()
