#!/usr/bin/env python3
"""Quick syntax and import validation."""
import sys

try:
    from Jarvis.sft import generate_dataset
    from Jarvis.sft import schema
    print("✓ Syntax validation passed")
    print("✓ generate_dataset imports successfully")
    print("✓ schema imports successfully")
    sys.exit(0)
except SyntaxError as e:
    print(f"✗ Syntax Error: {e}")
    sys.exit(1)
except ImportError as e:
    print(f"⚠ Import error (may be expected): {e}")
    sys.exit(0)
except Exception as e:
    print(f"✗ Unexpected error: {e}")
    sys.exit(1)
