#!/usr/bin/env python3
"""
Quick test to verify terminal module integration.
"""

import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("[TEST] Checking terminal module imports...")

try:
    from Jarvis.ui.terminal_branding import get_jarvis_logo_large, colorize_text, StatusColor
    print("  ✓ terminal_branding module loads")
except ImportError as e:
    print(f"  ✗ Failed to import terminal_branding: {e}")
    sys.exit(1)

try:
    from Jarvis.core.terminal_bridge import TerminalBridge, get_terminal_bridge
    print("  ✓ terminal_bridge module loads")
except ImportError as e:
    print(f"  ✗ Failed to import terminal_bridge: {e}")
    sys.exit(1)

try:
    # Only test PyQt6 import if we're not in GUI mode
    from Jarvis.ui.terminal_window import TerminalWindow
    print("  ✓ terminal_window module loads")
except ImportError as e:
    print(f"  ✗ Failed to import terminal_window: {e}")
    sys.exit(1)

try:
    from Jarvis.core.orchestrator import Orchestrator
    print("  ✓ orchestrator module loads (with terminal_bridge import)")
except ImportError as e:
    print(f"  ✗ Failed to import orchestrator: {e}")
    sys.exit(1)

print("\n[TEST] All terminal modules import successfully!")
print("\n[TEST] Testing terminal bridge signals...")

try:
    bridge = get_terminal_bridge()
    print(f"  ✓ Got terminal bridge instance: {type(bridge).__name__}")
    
    # Check signals exist
    assert hasattr(bridge, 'command_to_execute'), "Missing command_to_execute signal"
    assert hasattr(bridge, 'output_ready'), "Missing output_ready signal"
    assert hasattr(bridge, 'status_update'), "Missing status_update signal"
    assert hasattr(bridge, 'command_executed'), "Missing command_executed signal"
    print("  ✓ All terminal bridge signals present")
    
    # Check methods exist
    assert hasattr(bridge, 'on_command_started'), "Missing on_command_started method"
    assert hasattr(bridge, 'on_command_completed'), "Missing on_command_completed method"
    assert hasattr(bridge, 'on_status_changed'), "Missing on_status_changed method"
    print("  ✓ All terminal bridge methods present")
    
except Exception as e:
    print(f"  ✗ Terminal bridge test failed: {e}")
    sys.exit(1)

print("\n[TEST] All checks passed! Terminal integration is ready.")
print("\n[INFO] To test the full terminal UI, run:")
print("  python -m Jarvis.main")
