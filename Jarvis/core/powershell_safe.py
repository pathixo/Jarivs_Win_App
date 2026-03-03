"""
PowerShell Command Builder with Injection Protection
====================================================
Safe builders for PowerShell commands using proper escaping and argument arrays.
"""

import subprocess
import logging
from typing import List, Optional, Tuple
import os

from Jarvis.core.security_validator import InputValidator, sanitize_powershell_arg

logger = logging.getLogger("jarvis.security.powershell")


class SafePowerShellBuilder:
    """Safe PowerShell command builder preventing injection attacks."""
    
    @staticmethod
    def build_get_command(app_name: str) -> Tuple[bool, List[str], str]:
        """
        Safely build a Get-Command PowerShell command.
        
        Args:
            app_name: Application name to search for
            
        Returns:
            (success: bool, command_list: List[str], error: str)
            command_list is used with subprocess as an array (not shell injection)
        """
        # Validate app name
        is_valid, sanitized_name = InputValidator.validate_app_name(app_name)
        if not is_valid:
            return False, [], f"Invalid app name: {sanitized_name}"
        
        # Build PowerShell command as an array to prevent injection
        # Using -ArgumentList and variables to avoid string interpolation
        ps_script = (
            f"$appName = {sanitize_powershell_arg(sanitized_name)}; "
            "$result = @(); "
            "Get-Command -Name \"*$appName*\" -CommandType Application -ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty Source -First 1"
        )
        
        return True, ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script], ""
    
    @staticmethod
    def build_search_exe(base_dir: str, app_name: str) -> Tuple[bool, List[str], str]:
        """
        Safely build a Get-ChildItem PowerShell command for .exe search.
        
        Args:
            base_dir: Base directory to search in
            app_name: Application name pattern
            
        Returns:
            (success: bool, command_list: List[str], error: str)
        """
        # Validate inputs
        is_valid, error_msg = InputValidator.validate_file_path(base_dir)
        if not is_valid:
            return False, [], error_msg
        
        is_valid, sanitized_name = InputValidator.validate_app_name(app_name)
        if not is_valid:
            return False, [], f"Invalid app name"
        
        # Build safe PowerShell command using variables
        ps_script = (
            f"$basePath = {sanitize_powershell_arg(base_dir)}; "
            f"$pattern = {sanitize_powershell_arg(f'*{sanitized_name}*.exe')}; "
            "$result = @(); "
            "Get-ChildItem -Path $basePath -Filter $pattern -Recurse -Depth 2 "
            "-ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty FullName -First 1"
        )
        
        return True, ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script], ""
    
    @staticmethod
    def build_launch_process(exe_path: str, args: Optional[List[str]] = None) -> Tuple[bool, List[str], str]:
        """
        Safely build a Start-Process PowerShell command.
        
        Args:
            exe_path: Full path to executable
            args: Optional list of arguments
            
        Returns:
            (success: bool, command_list: List[str], error: str)
        """
        # Validate path
        is_valid, error_msg = InputValidator.validate_file_path(exe_path)
        if not is_valid:
            return False, [], error_msg
        
        if not os.path.exists(exe_path):
            return False, [], f"Executable not found: {exe_path}"
        
        # Build command using proper argument handling
        if args:
            # Build argument array as PowerShell array literal
            args_str = ", ".join(sanitize_powershell_arg(str(arg)) for arg in args)
            ps_script = (
                f"$exe = {sanitize_powershell_arg(exe_path)}; "
                f"$args = @({args_str}); "
                "Start-Process -FilePath $exe -ArgumentList $args"
            )
        else:
            ps_script = (
                f"$exe = {sanitize_powershell_arg(exe_path)}; "
                "Start-Process -FilePath $exe"
            )
        
        return True, ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script], ""
    
    @staticmethod
    def build_notify_action(title: str, message: str) -> Tuple[bool, List[str], str]:
        """
        Safely build a notification command.
        
        Args:
            title: Notification title
            message: Notification message
            
        Returns:
            (success: bool, command_list: List[str], error: str)
        """
        # Validate notification content
        is_valid, error_msg = InputValidator.validate_notification(title, message)
        if not is_valid:
            return False, [], error_msg
        
        # Use a safe method: Windows Toast notification via PowerShell
        # This avoids XML manipulation
        ps_script = (
            "[Windows.UI.Notifications.ToastNotificationManager, "
            "Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
            "[Windows.UI.Notifications.ToastNotification, "
            "Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
            "[Windows.Data.Xml.Dom.XmlDocument, "
            "Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null; "
            "$template = @\" "
            "<?xml version=\"1.0\"?> "
            "<toast> "
            "<visual> "
            "<binding template=\"ToastText02\"> "
            f"<text id=\"1\">{InputValidator.escape_powershell(title)}</text> "
            f"<text id=\"2\">{InputValidator.escape_powershell(message)}</text> "
            "</binding> "
            "</visual> "
            "</toast> "
            "\"@; "
            "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; "
            "$xml.LoadXml($template); "
            "$toast = New-Object Windows.UI.Notifications.ToastNotification $xml; "
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
            "'Jarvis').Show($toast)"
        )
        
        return True, ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script], ""


def run_safe_powershell(command_list: List[str], timeout: int = 5) -> Tuple[bool, str, str]:
    """
    Execute a PowerShell command safely from a command list (no shell injection).
    
    Args:
        command_list: Command as a list (first element is 'powershell')
        timeout: Timeout in seconds
        
    Returns:
        (success: bool, stdout: str, stderr: str)
    """
    try:
        result = subprocess.run(
            command_list,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        
        if result.returncode != 0:
            logger.warning("PowerShell command failed: %s", result.stderr[:200])
            return False, "", result.stderr
        
        return True, result.stdout.strip(), ""
    
    except subprocess.TimeoutExpired:
        return False, "", "Command timeout"
    except Exception as e:
        logger.error("PowerShell execution error: %s", e)
        return False, "", str(e)
