"""
Language Detection and Routing Module
======================================
Detects language (English vs Hindi) in user input and routes appropriately.
"""

import re
import logging
from typing import Tuple, Optional

logger = logging.getLogger("jarvis.nlu.language_detector")


class LanguageDetector:
    """Detects language in text with high accuracy."""
    
    # Hindi Devanagari Unicode ranges
    DEVANAGARI_RANGE = (0x0900, 0x097F)
    
    # Common Hindi words/phrases
    HINDI_KEYWORDS = {
        'नमस्ते': 'hello',
        'धन्यवाद': 'thank you',
        'फाइल': 'file',
        'खोलो': 'open',
        'बंद': 'close',
        'बनाओ': 'create',
        'हटाओ': 'delete',
        'सूची': 'list',
        'दिखाओ': 'show',
        'डायरेक्टरी': 'directory',
        'फाइलें': 'files',
        'सिस्टम': 'system',
        'जानकारी': 'information',
        'समय': 'time',
        'तारीख': 'date',
        'चलाओ': 'run',
        'प्रोग्राम': 'program',
        'एप्लिकेशन': 'application',
        'ब्राउज़र': 'browser',
        'खोज': 'search',
        'क्या': 'what',
        'कहाँ': 'where',
        'कौन': 'who',
        'कब': 'when',
        'कैसे': 'how',
        'मुझे': 'me',
        'हमें': 'us',
        'उसे': 'him/her',
        'उन्हें': 'them',
        'मेरा': 'my',
        'हमारा': 'our',
        'उसका': 'his/her',
        'उनका': 'their',
    }
    
    # Hindi Unicode range detection patterns
    HINDI_PATTERN = re.compile(f"[\u0900-\u097F]")
    
    # English-only pattern (basic ASCII)
    ENGLISH_ONLY_PATTERN = re.compile(r"^[a-zA-Z0-9\s\-._,!?'\"()]+$")
    
    @staticmethod
    def detect_devanagari_content(text: str) -> float:
        """
        Detect percentage of Devanagari (Hindi script) characters.
        
        Args:
            text: Text to analyze
            
        Returns:
            Percentage of Devanagari characters (0.0 to 1.0)
        """
        if not text:
            return 0.0
        
        devanagari_count = len(LanguageDetector.HINDI_PATTERN.findall(text))
        total_chars = len(text)
        return devanagari_count / total_chars if total_chars > 0 else 0.0
    
    @staticmethod
    def detect_hindi_words(text: str) -> float:
        """
        Detect Hindi keyword matches in text.
        
        Args:
            text: Text to analyze
            
        Returns:
            Confidence score (0.0 to 1.0) based on Hindi word density
        """
        if not text:
            return 0.0
        
        words = text.lower().split()
        hindi_word_count = 0
        
        for word in words:
            for hindi_keyword in LanguageDetector.HINDI_KEYWORDS.keys():
                if hindi_keyword in text:
                    hindi_word_count += 1
                    break
        
        return hindi_word_count / len(words) if words else 0.0
    
    @staticmethod
    def detect_language(text: str) -> Tuple[str, float]:
        """
        Detect language of input text with confidence score.
        
        Args:
            text: Text to detect language of
            
        Returns:
            (language: str, confidence: float)
            language: "hindi", "english", or "mixed"
            confidence: 0.0 to 1.0
        """
        if not text or not text.strip():
            return "english", 0.5
        
        # Check for Devanagari characters
        devanagari_pct = LanguageDetector.detect_devanagari_content(text)
        
        # Check for Hindi keywords
        hindi_word_score = LanguageDetector.detect_hindi_words(text)
        
        # Combined score for Hindi
        hindi_score = (devanagari_pct * 0.7) + (hindi_word_score * 0.3)
        
        # Decision logic
        if devanagari_pct > 0.05:  # Any Devanagari strongly suggests Hindi
            return "hindi", min(0.95, devanagari_pct + 0.2)
        elif hindi_word_score > 0.3:  # Multiple Hindi words
            return "hindi", min(0.85, hindi_word_score)
        elif hindi_score > 0.5:
            return "hindi", hindi_score
        else:
            return "english", 1.0 - hindi_score
    
    @staticmethod
    def is_hindi(text: str, threshold: float = 0.5) -> bool:
        """
        Quick check if text is Hindi.
        
        Args:
            text: Text to check
            threshold: Confidence threshold (default 0.5)
            
        Returns:
            True if detected language is Hindi with confidence >= threshold
        """
        language, confidence = LanguageDetector.detect_language(text)
        return language == "hindi" and confidence >= threshold


class LanguageRouter:
    """Routes requests to appropriate language pipeline."""
    
    def __init__(self):
        """Initialize router with language detection."""
        self._detector = LanguageDetector()
        self._language_preference = "auto"  # "auto", "en", "hi"
    
    def set_language_preference(self, preference: str) -> None:
        """
        Set user's language preference.
        
        Args:
            preference: "auto" (auto-detect), "en" (English), "hi" (Hindi)
        """
        if preference in ("auto", "en", "hi"):
            self._language_preference = preference
            logger.info("Language preference set to: %s", preference)
    
    def route_input(self, text: str) -> Tuple[str, float, str]:
        """
        Route input to appropriate language handler.
        
        Args:
            text: User input
            
        Returns:
            (language, confidence, target_handler)
            target_handler: "english_nlu", "hindi_nlu", "mixed_nlu"
        """
        if self._language_preference == "en":
            return "english", 1.0, "english_nlu"
        elif self._language_preference == "hi":
            return "hindi", 1.0, "hindi_nlu"
        
        # Auto-detect
        language, confidence = LanguageDetector.detect_language(text)
        
        if language == "hindi" and confidence > 0.6:
            return "hindi", confidence, "hindi_nlu"
        elif language == "english" and confidence > 0.6:
            return "english", confidence, "english_nlu"
        else:
            # Low confidence - treat as English with fallback
            return "mixed", confidence, "english_nlu"


class MultilingualContextManager:
    """Manages context in multiple languages."""
    
    def __init__(self):
        """Initialize context manager."""
        self._english_context = []
        self._hindi_context = []
        self._max_context_length = 20
    
    def add_english_context(self, text: str) -> None:
        """Add English conversation turn to context."""
        self._english_context.append(text)
        if len(self._english_context) > self._max_context_length:
            self._english_context.pop(0)
    
    def add_hindi_context(self, text: str) -> None:
        """Add Hindi conversation turn to context."""
        self._hindi_context.append(text)
        if len(self._hindi_context) > self._max_context_length:
            self._hindi_context.pop(0)
    
    def get_english_context(self, last_n: int = 5) -> str:
        """Get recent English context."""
        return "\n".join(self._english_context[-last_n:])
    
    def get_hindi_context(self, last_n: int = 5) -> str:
        """Get recent Hindi context."""
        return "\n".join(self._hindi_context[-last_n:])
    
    def clear_context(self) -> None:
        """Clear all context."""
        self._english_context = []
        self._hindi_context = []
