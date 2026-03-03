#!/usr/bin/env python3
"""Quick syntax verification test for indentation fix."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    # Test import of the fixed module
    from Jarvis.core.language_detector import LanguageDetector, LanguageRouter
    print("✅ Import successful: language_detector.py syntax is valid")
    
    # Quick functionality test
    result = LanguageDetector.detect_hindi_script("नमस्ते")
    print(f"✅ detect_hindi_script() works: Hindi script detection = {result:.1%}")
    
    # Test detect_language
    lang, conf = LanguageDetector.detect_language("hello")
    print(f"✅ detect_language() works: 'hello' detected as '{lang}' ({conf:.0%} confidence)")
    
    # Test LanguageRouter
    router = LanguageRouter()
    print("✅ LanguageRouter instantiated successfully")
    
    print("\n🎉 All syntax checks passed - Jarvis should start now!")
    sys.exit(0)
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
