"""
Credential Protection Module
============================
Secure handling of API keys and credentials.
"""

import logging
import re
from typing import Dict, Optional
import os

logger = logging.getLogger("jarvis.security.credentials")


class CredentialProtection:
    """Protects API keys and sensitive credentials from leakage."""
    
    # Patterns for detecting common credentials
    CREDENTIAL_PATTERNS = [
        (r"sk-[a-zA-Z0-9]{20,}", "OpenAI API key"),
        (r"pk-[a-zA-Z0-9]{20,}", "Potential API key"),
        (r"password\s*[=:]\s*['\"][^'\"]+['\"]", "Password literal"),
        (r"api[_-]?key\s*[=:]\s*['\"][^'\"]+['\"]", "API key literal"),
        (r"token\s*[=:]\s*['\"][^'\"]+['\"]", "Token literal"),
        (r"secret\s*[=:]\s*['\"][^'\"]+['\"]", "Secret literal"),
    ]
    
    @staticmethod
    def mask_credential(credential: str, visible_chars: int = 4) -> str:
        """
        Mask a credential for logging.
        
        Args:
            credential: The credential to mask
            visible_chars: How many characters to show at start and end
            
        Returns:
            Masked credential (e.g., "sk-****...****")
        """
        if len(credential) <= visible_chars * 2:
            return "*" * len(credential)
        
        start = credential[:visible_chars]
        end = credential[-visible_chars:]
        middle_len = len(credential) - (visible_chars * 2)
        return f"{start}{'*' * middle_len}{end}"
    
    @staticmethod
    def scan_for_credentials(text: str) -> list:
        """
        Scan text for potential credential leaks.
        
        Args:
            text: Text to scan
            
        Returns:
            List of (match, credential_type) tuples
        """
        findings = []
        for pattern, cred_type in CredentialProtection.CREDENTIAL_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                findings.append((match.group(), cred_type))
        return findings
    
    @staticmethod
    def redact_credentials(text: str) -> str:
        """
        Redact credentials from text (for logging/display).
        
        Args:
            text: Text potentially containing credentials
            
        Returns:
            Text with credentials redacted
        """
        for pattern, _ in CredentialProtection.CREDENTIAL_PATTERNS:
            text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)
        
        # Also redact common API key environments
        text = re.sub(r"(Authorization:\s*Bearer\s+)[^\s\n]+", r"\1[REDACTED]", text)
        text = re.sub(r"(X-API-Key:\s*)[^\s\n]+", r"\1[REDACTED]", text)
        return text
    
    @staticmethod
    def sanitize_url(url: str) -> str:
        """
        Remove credentials from URLs.
        
        Args:
            url: URL potentially containing credentials
            
        Returns:
            URL with credentials removed
        """
        # Remove basic auth (user:pass@host -> host)
        url = re.sub(r"://[^:]+:[^@]+@", "://", url)
        
        # Remove API keys from query strings
        url = re.sub(r"([?&])key=[^&]*", r"\1key=[REDACTED]", url)
        url = re.sub(r"([?&])api[_-]key=[^&]*", r"\1api_key=[REDACTED]", url)
        url = re.sub(r"([?&])token=[^&]*", r"\1token=[REDACTED]", url)
        
        return url


class SecureConfigLoader:
    """Securely loads configuration from environment."""
    
    # Recognized API key environment variables
    PROTECTED_ENV_VARS = [
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "GROK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "PORCUPINE_ACCESS_KEY",
    ]
    
    @staticmethod
    def get_api_key(env_var: str, required: bool = False) -> Optional[str]:
        """
        Safely retrieve an API key from environment.
        
        Args:
            env_var: Environment variable name
            required: Whether to raise error if missing
            
        Returns:
            API key or None
        """
        key = os.getenv(env_var)
        
        if required and not key:
            raise ValueError(f"Missing required API key: {env_var}")
        
        if key:
            logger.info(f"Loaded {env_var}: {CredentialProtection.mask_credential(key)}")
        
        return key
    
    @staticmethod
    def validate_api_key(key: str, env_var: str, pattern: Optional[str] = None) -> bool:
        """
        Validate an API key format.
        
        Args:
            key: API key to validate
            env_var: Environment variable name (for logging)
            pattern: Optional regex pattern to validate against
            
        Returns:
            True if valid
        """
        if not key or len(key) < 8:
            logger.warning(f"{env_var} appears invalid (too short)")
            return False
        
        if pattern and not re.match(pattern, key):
            logger.warning(f"{env_var} does not match expected format")
            return False
        
        return True


class HTTPHeaderSanitizer:
    """Sanitizes HTTP headers for logging."""
    
    SENSITIVE_HEADERS = [
        "Authorization",
        "X-API-Key",
        "X-Auth-Token",
        "Cookie",
        "Set-Cookie",
    ]
    
    @staticmethod
    def sanitize_headers(headers: Dict[str, str]) -> Dict[str, str]:
        """
        Create a sanitized copy of headers for logging.
        
        Args:
            headers: HTTP headers dict
            
        Returns:
            Copy with sensitive values redacted
        """
        sanitized = {}
        for key, value in headers.items():
            if key in HTTPHeaderSanitizer.SENSITIVE_HEADERS:
                sanitized[key] = CredentialProtection.mask_credential(str(value))
            else:
                sanitized[key] = value
        return sanitized
