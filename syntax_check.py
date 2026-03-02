#!/usr/bin/env python3
"""Syntax check for terminal modules."""
import py_compile
import sys

files_to_check = [
    r"D:\Coding\Projects\Antigravity\Jarvis\ui\terminal_branding.py",
    r"D:\Coding\Projects\Antigravity\Jarvis\ui\terminal_window.py",
    r"D:\Coding\Projects\Antigravity\Jarvis\core\terminal_bridge.py",
]

print("[CHECK] Verifying Python syntax...")
all_ok = True

for filepath in files_to_check:
    try:
        py_compile.compile(filepath, doraise=True)
        print(f"  ✓ {filepath.split(chr(92))[-1]}")
    except py_compile.PyCompileError as e:
        print(f"  ✗ {filepath.split(chr(92))[-1]}: {e}")
        all_ok = False

if all_ok:
    print("\n[OK] All files have valid syntax!")
    sys.exit(0)
else:
    print("\n[ERROR] Syntax errors found!")
    sys.exit(1)
