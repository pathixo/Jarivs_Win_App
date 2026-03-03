"""
Hindi Intent Classification Module
===================================
Classifies Hindi commands and natural language to intents.
Maps Hindi requests to Jarvis actions.
"""

import re
import logging
from typing import Tuple, List, Optional

logger = logging.getLogger("jarvis.nlu.hindi_classifier")


class HindiIntentClassifier:
    """Classifies Hindi user input to action intents."""
    
    # Hindi command patterns with intent mapping
    HINDI_INTENT_PATTERNS = {
        # File operations
        "फाइल_खोलो": (r"फाइल\s+(खोलो|खुलवाओ|दिखाओ)", "open_file"),
        "फाइल_बनाओ": (r"फाइल\s+(बनाओ|बनवाओ|बनाई)", "create_file"),
        "फाइल_हटाओ": (r"फाइल\s+(हटाओ|मिटाओ|हटवाओ|डिलीट)", "delete_file"),
        "फाइल_देखो": (r"फाइल\s+(देखो|दिखाओ|सूची)", "list_files"),
        
        # Directory operations
        "डायरेक्टरी_खोलो": (r"डायरेक्टरी\s+(खोलो|दिखाओ)", "open_directory"),
        "डायरेक्टरी_बनाओ": (r"डायरेक्टरी\s+(बनाओ|बनवाओ)", "create_directory"),
        "डायरेक्टरी_हटाओ": (r"डायरेक्टरी\s+(हटाओ|मिटाओ)", "delete_directory"),
        
        # Application launching
        "एप्लिकेशन_खोलो": (r"(एप्लिकेशन|ऐप|प्रोग्राम)\s+([^\s]+)\s+(खोलो|चलाओ|शुरू)", "launch_app"),
        "ब्राउज़र_खोलो": (r"ब्राउज़र\s+(खोलो|चलाओ)", "launch_browser"),
        
        # System information
        "सिस्टम_जानकारी": (r"सिस्टम\s+जानकारी", "get_system_info"),
        "समय": (r"(समय|वक़्त|टाइम)\s+(क्या|बताओ)", "get_time"),
        "तारीख": (r"तारीख\s+(क्या|बताओ)", "get_date"),
        
        # Search operations
        "खोज": (r"(खोज|सर्च)\s+करो", "search_system"),
        "प्रक्रिया_देखो": (r"प्रक्रिया\s+(देखो|सूची)", "list_processes"),
        
        # Help and status
        "मदद": (r"(मदद|सहायता)\s+(दो|चाहिए)", "help"),
        "स्थिति": (r"स्थिति\s+(क्या|बताओ)", "status"),
        
        # Web operations
        "वेबसाइट_खोलो": (r"(वेबसाइट|साइट|URL)\s+([^\s]+)\s+(खोलो|दिखाओ)", "open_url"),
    }
    
    # General Hindi question patterns
    HINDI_QUESTION_PATTERNS = {
        "what": r"क्या",
        "where": r"कहाँ",
        "who": r"कौन",
        "when": r"कब",
        "how": r"कैसे",
        "why": r"क्यों",
    }
    
    # Action verbs in Hindi
    HINDI_ACTION_VERBS = {
        "खोलो": "open",
        "चलाओ": "run/launch",
        "बनाओ": "create",
        "हटाओ": "delete",
        "दिखाओ": "show",
        "सूची": "list",
        "खोज": "search",
        "बताओ": "tell/inform",
        "देखो": "see/look",
        "करो": "do/perform",
        "मिटाओ": "erase/delete",
        "शुरू": "start",
        "बंद": "stop/close",
    }
    
    @staticmethod
    def classify_hindi_intent(text: str) -> Tuple[str, float, Optional[dict]]:
        """
        Classify Hindi text to an intent.
        
        Args:
            text: Hindi text input
            
        Returns:
            (intent: str, confidence: float, parameters: dict)
            intent: action identifier (e.g., "open_file", "launch_app")
            confidence: 0.0 to 1.0
            parameters: extracted parameters (e.g., filename, app name)
        """
        if not text:
            return "unknown", 0.0, None
        
        text_lower = text.lower().strip()
        best_intent = "unknown"
        best_confidence = 0.0
        best_params = None
        
        # Check against known patterns
        for pattern_name, (pattern_regex, intent_name) in HindiIntentClassifier.HINDI_INTENT_PATTERNS.items():
            match = re.search(pattern_regex, text_lower, re.IGNORECASE)
            if match:
                # Calculate confidence based on match
                confidence = 0.95  # High confidence for exact pattern match
                params = HindiIntentClassifier._extract_parameters(text_lower, intent_name, match)
                
                if confidence > best_confidence:
                    best_intent = intent_name
                    best_confidence = confidence
                    best_params = params
        
        # If no specific pattern found, try action verb detection
        if best_intent == "unknown":
            for hindi_verb, english_verb in HindiIntentClassifier.HINDI_ACTION_VERBS.items():
                if hindi_verb in text_lower:
                    best_intent = f"action_{english_verb}"
                    best_confidence = 0.6
                    break
        
        return best_intent, best_confidence, best_params
    
    @staticmethod
    def _extract_parameters(text: str, intent: str, match) -> dict:
        """
        Extract parameters from matched text.
        
        Args:
            text: Full input text
            intent: Intent name
            match: Regex match object
            
        Returns:
            Dictionary of extracted parameters
        """
        params = {"intent": intent}
        
        # Extract filename/dirname if present
        file_patterns = [
            r"फाइल\s+(\S+)",
            r"डायरेक्टरी\s+(\S+)",
            r"नाम\s+(\S+)",
        ]
        for pattern in file_patterns:
            m = re.search(pattern, text)
            if m:
                params["name"] = m.group(1)
                break
        
        # Extract app name if present
        app_pattern = r"(एप्लिकेशन|ऐप|प्रोग्राम)\s+([^\s]+)"
        m = re.search(app_pattern, text)
        if m:
            params["app_name"] = m.group(2)
        
        return params
    
    @staticmethod
    def translate_hindi_to_english(text: str) -> str:
        """
        Translate Hindi keywords to English for command execution.
        
        Args:
            text: Hindi text
            
        Returns:
            Text with Hindi words replaced by English equivalents
        """
        result = text.lower()
        
        # Replace common Hindi verbs
        for hindi_verb, english_verb in HindiIntentClassifier.HINDI_ACTION_VERBS.items():
            result = result.replace(hindi_verb, english_verb)
        
        # Replace noun patterns
        replacements = {
            "फाइल": "file",
            "डायरेक्टरी": "directory",
            "एप्लिकेशन": "application",
            "ऐप": "app",
            "प्रोग्राम": "program",
            "ब्राउज़र": "browser",
            "सिस्टम": "system",
            "जानकारी": "information",
            "समय": "time",
            "तारीख": "date",
            "सूची": "list",
            "खोज": "search",
        }
        
        for hindi, english in replacements.items():
            result = result.replace(hindi, english)
        
        return result
    
    @staticmethod
    def get_hindi_system_prompt() -> str:
        """
        Get system prompt for Hindi language mode.
        
        Returns:
            System prompt for Hindi conversation
        """
        return """आप एक सहायक एआई असिस्टेंट (Jarvis) हैं जो हिंदी में बातचीत करते हैं।

आपके निर्देश:
1. यूजर के सवालों का जवाब हिंदी में दें
2. कमांड को [SHELL:...[/SHELL:...] टैग में दें
3. फाइल ऑपरेशन को [ACTION:...[/ACTION:...] में दें
4. हमेशा स्पष्ट और संक्षिप्त जवाब दें
5. तकनीकी शब्दों के लिए अंग्रेजी का उपयोग करें यदि आवश्यक हो

उदाहरण:
यूजर: "फाइलें दिखाओ"
आप: "ठीक है, आपकी फाइलें दिखाता हूँ।
[ACTION:list_files]करंट डायरेक्टरी में फाइलें[/ACTION:list_files]"
"""


class HindiNLUPipeline:
    """Complete Hindi NLU processing pipeline."""
    
    def __init__(self):
        """Initialize pipeline."""
        self._classifier = HindiIntentClassifier()
    
    def process_hindi_input(self, text: str) -> dict:
        """
        Process Hindi input through full NLU pipeline.
        
        Args:
            text: Hindi input
            
        Returns:
            Dictionary with:
            - intent: Classified intent
            - confidence: Confidence score
            - parameters: Extracted parameters
            - english_translation: English translation
            - system_prompt: System prompt for this language
        """
        intent, confidence, parameters = HindiIntentClassifier.classify_hindi_intent(text)
        english_translation = HindiIntentClassifier.translate_hindi_to_english(text)
        
        return {
            "language": "hindi",
            "original_text": text,
            "intent": intent,
            "confidence": confidence,
            "parameters": parameters or {},
            "english_translation": english_translation,
            "system_prompt": HindiIntentClassifier.get_hindi_system_prompt(),
        }
