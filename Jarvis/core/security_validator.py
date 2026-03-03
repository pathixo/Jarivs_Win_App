"""
Security Input Validation Module
==================================
Validates all user input before processing to prevent injection attacks,
path traversal, and other security vulnerabilities.
"""

import re
import os
from pathlib import Path
from typing import Tuple
import logging

logger = logging.getLogger("jarvis.security.validator")


class InputValidator:
    """Validates user input for security threats."""
    
    # Sensitive file patterns that should not be accessed
    SENSITIVE_PATH_PATTERNS = [
        r"(?i)^[a-z]:\\windows\\",
        r"(?i)^[a-z]:\\program files",
        r"(?i)appdata\\local\\microsoft",
        r"(?i)ntuser\.dat",
        r"(?i)c:\\users\\.*\\ntuser\.dat",
    ]
    
    # PowerShell dangerous characters that need escaping
    POWERSHELL_SPECIAL_CHARS = {
        "'": "''",      # Escape single quotes by doubling
        "$": "`$",      # Escape dollar sign
        "`": "``",      # Escape backticks
        '"': '`"',      # Escape double quotes
        ";": "`;",      # Escape semicolon
        "\n": "`n",     # Escape newlines
        "\r": "`r",     # Escape carriage returns
    }
    
    @staticmethod
    def escape_powershell(text: str) -> str:
        """
        Escape special PowerShell characters to prevent command injection.
        
        Args:
            text: User-provided string to escape
            
        Returns:
            Escaped string safe for PowerShell interpolation
        """
        if not isinstance(text, str):
            return str(text)
        
        result = text
        for char, replacement in InputValidator.POWERSHELL_SPECIAL_CHARS.items():
            result = result.replace(char, replacement)
        return result
    
    @staticmethod
    def validate_file_path(path: str, allow_parent: bool = False) -> Tuple[bool, str]:
        """
        Validate a file path is safe to access.
        
        Args:
            path: File path to validate
            allow_parent: Whether to allow accessing parent directories
            
        Returns:
            (is_valid, error_message)
        """
        if not isinstance(path, str) or not path.strip():
            return False, "Path cannot be empty"
        
        # Normalize the path
        try:
            norm_path = os.path.normpath(os.path.abspath(path))
        except (OSError, ValueError) as e:
            return False, f"Invalid path: {e}"
        
        # Check for path traversal attempts
        if not allow_parent and ".." in path:
            return False, "Path traversal (..) not allowed"
        
        # Check for sensitive system paths
        for pattern in InputValidator.SENSITIVE_PATH_PATTERNS:
            if re.search(pattern, norm_path):
                return False, f"Access to system path blocked: {norm_path}"
        
        # Block access to Windows system directories
        windows_protected = [
            "C:\\Windows",
            "C:\\Windows\\System32",
            "C:\\Windows\\System32\\drivers\\etc",
            "C:\\Program Files",
            "C:\\Program Files (x86)",
            "C:\\ProgramData",
        ]
        
        for protected in windows_protected:
            if norm_path.lower().startswith(protected.lower()):
                return False, f"Access to protected directory blocked: {protected}"
        
        return True, ""
    
    @staticmethod
    def validate_app_name(app_name: str) -> Tuple[bool, str]:
        """
        Validate app name to prevent command injection.
        
        Args:
            app_name: Application name to validate
            
        Returns:
            (is_valid, sanitized_name)
        """
        if not isinstance(app_name, str) or not app_name.strip():
            return False, ""
        
        # Remove/reject dangerous PowerShell metacharacters
        dangerous_patterns = [
            r"[;|&$`\n\r]",  # Command separators and special chars
            r"'.*'",          # Single-quoted strings
            r'".*"',          # Double-quoted strings
            r"\$\{.*\}",      # Variable expansion
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, app_name):
                return False, f"App name contains dangerous characters: {pattern}"
        
        # Whitelist: only allow alphanumeric, spaces, hyphens, underscores, dots
        if not re.match(r"^[a-zA-Z0-9\s\-_.]+$", app_name):
            return False, f"App name contains invalid characters"
        
        return True, app_name.strip()
    
    @staticmethod
    def validate_command_string(cmd: str, max_length: int = 1024) -> Tuple[bool, str]:
        """
        Validate a command string for dangerous patterns.
        
        Args:
            cmd: Command string to validate
            max_length: Maximum allowed command length
            
        Returns:
            (is_safe, error_message)
        """
        if not isinstance(cmd, str):
            return False, "Command must be a string"
        
        if len(cmd) > max_length:
            return False, f"Command too long (max {max_length} chars)"
        
        # Check for command chaining attempts
        chain_patterns = [
            r";\s*[a-z]",           # Command separator
            r"\|\s*[a-z]",          # Pipe
            r"&&\s*[a-z]",          # AND operator
            r"\|\|\s*[a-z]",        # OR operator
        ]
        
        for pattern in chain_patterns:
            if re.search(pattern, cmd, re.IGNORECASE):
                return False, "Command chaining not allowed"
        
        return True, ""
    
    @staticmethod
    def validate_notification(title: str, message: str) -> Tuple[bool, str]:
        """
        Validate notification text to prevent injection.
        
        Args:
            title: Notification title
            message: Notification message
            
        Returns:
            (is_valid, error_message)
        """
        max_title_len = 256
        max_msg_len = 512
        
        if len(title) > max_title_len:
            return False, f"Title too long (max {max_title_len} chars)"
        
        if len(message) > max_msg_len:
            return False, f"Message too long (max {max_msg_len} chars)"
        
        # Check for dangerous XML/PS characters
        dangerous = r"[<>\"'`$;|&\n]"
        if re.search(dangerous, title) or re.search(dangerous, message):
            return False, "Notification contains dangerous characters"
        
        return True, ""


class SessionTokenGenerator:
    """Generates unique session tokens for tag validation."""
    
    @staticmethod
    def generate_tag_token() -> str:
        """
        Generate a unique random token for tag validation.
        
        Returns:
            Random 32-character hex token
        """
        import secrets
        return secrets.token_hex(16)  # 32 chars


def sanitize_powershell_arg(arg: str) -> str:
    """
    Sanitize a single PowerShell argument.
    
    Wraps argument in single quotes and escapes internal quotes.
    
    Args:
        arg: Argument to sanitize
        
    Returns:
        Sanitized argument safe for PowerShell
    """
    if not isinstance(arg, str):
        arg = str(arg)
    
    # Escape single quotes by doubling them
    escaped = arg.replace("'", "''")
    # Wrap in single quotes
    return f"'{escaped}'"
