#!/usr/bin/env python3
"""
Test Suite: Language Restriction (Phase 1)

Validates that only Hindi (hi) and English (en) are accepted across all modules:
- language_detector.py
- stt_router.py
- tts.py
- orchestrator.py
"""

import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_language_restriction")

def test_language_detector():
    """Test that language_detector only returns en/hi."""
    from Jarvis.core.language_detector import LanguageDetector, LanguageRouter
    
    print("\n✓ Testing LanguageDetector...")
    
    # Test English detection
    result, conf = LanguageDetector.detect_language("Hello, how are you today?")
    assert result == "en", f"Expected 'en', got '{result}'"
    print(f"  ✓ English detected: {result} ({conf:.2f})")
    
    # Test Hindi detection
    result, conf = LanguageDetector.detect_language("नमस्ते, आप कैसे हो?")
    assert result == "hi", f"Expected 'hi', got '{result}'"
    print(f"  ✓ Hindi detected: {result} ({conf:.2f})")
    
    # Test unknown language (should default to en)
    result, conf = LanguageDetector.detect_language("Bonjour, comment allez-vous?")
    assert result == "en", f"Expected 'en' for unknown language, got '{result}'"
    print(f"  ✓ Unknown language defaults to en: {result}")
    
    # Test is_hindi
    assert LanguageDetector.is_hindi("नमस्ते")
    print("  ✓ is_hindi() works correctly")
    
    # Test LanguageRouter
    print("\n✓ Testing LanguageRouter...")
    router = LanguageRouter()
    
    # Test valid language preferences
    assert router.set_language_preference("en")
    assert router.set_language_preference("hi")
    assert router.set_language_preference("auto")
    print("  ✓ Valid language preferences accepted (en, hi, auto)")
    
    # Test invalid language preferences
    assert not router.set_language_preference("fr")
    assert not router.set_language_preference("es")
    print("  ✓ Invalid language preferences rejected (fr, es, etc)")
    
    # Test routing
    lang, conf, handler = router.route_input("Hello world")
    assert lang == "en"
    assert handler == "english_nlu"
    print(f"  ✓ English routing: {lang} → {handler}")
    
    lang, conf, handler = router.route_input("नमस्ते")
    assert lang == "hi"
    assert handler == "hindi_nlu"
    print(f"  ✓ Hindi routing: {lang} → {handler}")


def test_stt_router():
    """Test that STTRouter validates language codes."""
    from Jarvis.input.stt_router import STTRouter
    import os
    
    print("\n✓ Testing STTRouter...")
    
    # Check supported languages constant
    assert "en" in STTRouter.SUPPORTED_LANGUAGES
    assert "hi" in STTRouter.SUPPORTED_LANGUAGES
    assert "auto" in STTRouter.SUPPORTED_LANGUAGES
    print(f"  ✓ Supported languages: {sorted(STTRouter.SUPPORTED_LANGUAGES)}")
    
    # Create router with dummy API keys (won't actually use them)
    router = STTRouter(groq_api_key="dummy", gemini_api_key="dummy", stt_provider="local")
    
    # Test valid language setting
    assert router.set_language("en")
    assert router.set_language("hi")
    assert router.set_language("auto")
    print("  ✓ Valid languages accepted (en, hi, auto)")
    
    # Test invalid language setting
    assert not router.set_language("fr")
    assert not router.set_language("es")
    assert not router.set_language("mixed")
    print("  ✓ Invalid languages rejected (fr, es, mixed, etc)")


def test_tts():
    """Test that TTS only accepts en/hi language modes."""
    from Jarvis.output.tts import TTS
    
    print("\n✓ Testing TTS...")
    
    tts = TTS()
    
    # Test valid language modes
    assert tts.set_language_mode("en")
    assert tts.set_language_mode("hi")
    assert tts.set_language_mode("auto")
    print("  ✓ Valid language modes accepted (en, hi, auto)")
    
    # Test invalid language modes
    assert not tts.set_language_mode("fr")
    assert not tts.set_language_mode("spanish")
    assert not tts.set_language_mode("mixed")
    print("  ✓ Invalid language modes rejected (fr, spanish, mixed, etc)")
    
    # Cleanup
    tts.close()


def test_orchestrator_voice_command():
    """Test that orchestrator restricts voice language commands to en/hi."""
    from Jarvis.core.orchestrator import Orchestrator
    
    print("\n✓ Testing Orchestrator voice commands...")
    
    orch = Orchestrator()
    
    # Test valid voice language commands
    result = orch._handle_voice_command("voice language en")
    assert "set to" in result.lower() and "error" not in result.lower()
    print(f"  ✓ 'voice language en': {result.split(':')[0]}")
    
    result = orch._handle_voice_command("voice language hi")
    assert "set to" in result.lower() and "error" not in result.lower()
    print(f"  ✓ 'voice language hi': {result.split(':')[0]}")
    
    result = orch._handle_voice_command("voice language auto")
    assert "set to" in result.lower() and "error" not in result.lower()
    print(f"  ✓ 'voice language auto': {result.split(':')[0]}")
    
    # Test invalid voice language commands
    result = orch._handle_voice_command("voice language french")
    assert "error" in result.lower() or "unsupported" in result.lower()
    print(f"  ✓ 'voice language french' rejected: Error detected")
    
    result = orch._handle_voice_command("voice language spanish")
    assert "error" in result.lower() or "unsupported" in result.lower()
    print(f"  ✓ 'voice language spanish' rejected: Error detected")


def test_orchestrator_stt_command():
    """Test that orchestrator restricts STT language commands to en/hi."""
    from Jarvis.core.orchestrator import Orchestrator
    
    print("\n✓ Testing Orchestrator STT commands...")
    
    orch = Orchestrator()
    
    # Test STT language list
    result = orch._handle_stt_command("stt language list")
    assert "en" in result.lower() and "hi" in result.lower()
    assert "restricted" in result.lower() or "english" in result.lower()
    print(f"  ✓ 'stt language list' shows only en/hi")
    
    # Test invalid STT language commands
    result = orch._handle_stt_command("stt language french")
    assert "error" in result.lower() or "unsupported" in result.lower()
    print(f"  ✓ 'stt language french' rejected: Error detected")
    
    result = orch._handle_stt_command("stt language german")
    assert "error" in result.lower() or "unsupported" in result.lower()
    print(f"  ✓ 'stt language german' rejected: Error detected")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("PHASE 1: LANGUAGE RESTRICTION TESTS")
    print("="*60)
    
    try:
        test_language_detector()
        test_stt_router()
        test_tts()
        test_orchestrator_voice_command()
        test_orchestrator_stt_command()
        
        print("\n" + "="*60)
        print("✓ ALL TESTS PASSED!")
        print("="*60)
        print("\nPhase 1 Complete: Language restriction to Hindi/English only")
        return 0
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        logger.exception("Test failure:")
        return 1


if __name__ == "__main__":
    sys.exit(main())
