import py_compile
import sys

try:
    py_compile.compile(r'D:\Coding\Projects\Antigravity\Jarvis\core\language_detector.py', doraise=True)
    print("✅ language_detector.py: Syntax valid")
    sys.exit(0)
except py_compile.PyCompileError as e:
    print(f"❌ Syntax error: {e}")
    sys.exit(1)
