import sys
import os
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.getcwd())

from Jarvis.core.system.windows import WindowsBackend

def test_app_discovery():
    backend = WindowsBackend()
    
    # Mock subprocess.run to simulate Get-Command finding something
    with patch("subprocess.run") as mock_run:
        # Mock 1: Get-Command finds 'code'
        mock_run.return_value = MagicMock(stdout=r"C:\Users\HP\AppData\Local\Programs\Microsoft VS Code\Code.exe")
        
        # Test finding an app that isn't in registry
        # We need to make sure registry lookup fails
        backend._app_registry.resolve = MagicMock(return_value=None)
        
        # We also need to patch os.path.exists to return True for our fake path
        with patch("os.path.exists", return_value=True):
            path = backend._find_app_path("vscode")
            assert path == r"C:\Users\HP\AppData\Local\Programs\Microsoft VS Code\Code.exe"
            print("App discovery via Get-Command passed!")

    # Test recursive search fallback
    with patch("subprocess.run") as mock_run:
        # Mock 1: Get-Command fails
        # Mock 2: Get-ChildItem finds something in Program Files
        mock_run.side_effect = [
            MagicMock(stdout=""), # Get-Command fails
            MagicMock(stdout=r"C:\Program Files\Example\Example.exe"), # Get-ChildItem 1 (Program Files)
            MagicMock(stdout=""), # Get-ChildItem 2 (x86)
            MagicMock(stdout="")  # Get-ChildItem 3 (Local)
        ]
        
        with patch("os.path.exists") as mock_exists:
            # We need to handle multiple calls to exists
            # Program Files exists, but the fake path also exists
            def side_effect(p):
                if "Program Files" in p: return True
                if "Example.exe" in p: return True
                return False
            mock_exists.side_effect = side_effect
            
            path = backend._find_app_path("example")
            assert path == r"C:\Program Files\Example\Example.exe"
            print("App discovery via recursive search passed!")

if __name__ == "__main__":
    test_app_discovery()
