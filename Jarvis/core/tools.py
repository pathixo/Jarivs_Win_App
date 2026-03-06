"""
Tools Module — Sandboxed File & Terminal Operations
=====================================================
Implements workspace-sandboxed file system and command operations.
Delegates all OS interactions through the SystemBackend abstraction.
"""

import math
import os
from typing import Optional

from Jarvis.core.system.backend import SystemBackend
from Jarvis.core.telemetry import get_telemetry, AgentPhase, TelemetryType


class Tools:
    """
    Implements local tools for file system and terminal operations.
    Enforces sandboxing within the 'workspace' directory.
    Delegates to SystemBackend for all OS interactions.
    """
    def __init__(self, backend: Optional[SystemBackend] = None):
        # Define workspace directory relative to project root
        self.workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../workspace"))
        if not os.path.exists(self.workspace_dir):
            os.makedirs(self.workspace_dir)
            print(f"Created workspace directory at: {self.workspace_dir}")

        # SystemBackend for OS operations (lazy-initialized if not provided)
        self._backend = backend
        self.telemetry = get_telemetry()

    @property
    def backend(self) -> SystemBackend:
        """Lazy-init backend if not provided at construction time."""
        if self._backend is None:
            from Jarvis.core.system import get_backend
            self._backend = get_backend()
        return self._backend

    def _is_safe_path(self, filepath):
        """
        Ensures the path is within the workspace directory.
        """
        try:
            # Resolve absolute path
            abs_path = os.path.abspath(os.path.join(self.workspace_dir, filepath))
            # Check if it starts with workspace_dir
            return abs_path.startswith(self.workspace_dir), abs_path
        except Exception:
            return False, None

    def execute_terminal_command(self, command):
        """
        Executes a shell command via SystemBackend and returns output.
        """
        result = self.backend.run_shell(command, cwd=self.workspace_dir)
        if result.success:
            return f"Output:\n{result.stdout}" if result.stdout else "Command executed."
        else:
            return f"Error:\n{result.error}" if result.error else f"Error:\n{result.message}"
    
    def list_files(self, directory="."):
        """
        Lists files in the specified directory (relative to workspace).
        """
        self.telemetry.tool_start("File System", f"list_files {directory}")
        safe, abs_path = self._is_safe_path(directory)
        if not safe:
            self.telemetry.tool_end("File System", "Access denied", success=False)
            return "Error: Access denied. Path is outside workspace."
            
        result = self.backend.list_dir(abs_path)
        self.telemetry.tool_end("File System", result.output if result.success else result.error, success=result.success)
        if result.success:
            return result.output
        return f"Error listing files: {result.error}"
    
    def read_file(self, filepath):
        """
        Reads content of a text file (relative to workspace).
        """
        self.telemetry.tool_start("File System", f"read_file {filepath}")
        safe, abs_path = self._is_safe_path(filepath)
        if not safe:
            self.telemetry.tool_end("File System", "Access denied", success=False)
            return "Error: Access denied. Path is outside workspace."

        result = self.backend.read_file(abs_path)
        self.telemetry.tool_end("File System", f"Read {len(result.output)} chars" if result.success else result.error, success=result.success)
        if result.success:
            return result.output
        return f"Error reading file: {result.error}"

    def write_file(self, filepath, content):
        """
        Writes content to a file (relative to workspace). Overwrites if exists.
        """
        self.telemetry.tool_start("File System", f"write_file {filepath}")
        safe, abs_path = self._is_safe_path(filepath)
        if not safe:
            self.telemetry.tool_end("File System", "Access denied", success=False)
            return "Error: Access denied. Path is outside workspace."

        result = self.backend.write_file(abs_path, content)
        self.telemetry.tool_end("File System", "Success" if result.success else result.error, success=result.success)
        if result.success:
            return f"File '{filepath}' written successfully."
        return f"Error writing file: {result.error}"

    def calculate(self, expression: str) -> str:
        """
        Safely evaluates a mathematical expression using Python's eval
        with a restricted namespace (math functions only, no builtins).
        """
        # Whitelist: only math functions and safe builtins
        allowed = {
            "__builtins__": {},
            "abs": abs, "round": round, "min": min, "max": max, "pow": pow,
            "int": int, "float": float, "sum": sum, "len": len,
            # math module functions
            "sqrt": math.sqrt, "ceil": math.ceil, "floor": math.floor,
            "log": math.log, "log10": math.log10, "log2": math.log2,
            "sin": math.sin, "cos": math.cos, "tan": math.tan,
            "asin": math.asin, "acos": math.acos, "atan": math.atan,
            "pi": math.pi, "e": math.e, "inf": math.inf,
            "degrees": math.degrees, "radians": math.radians,
            "factorial": math.factorial, "gcd": math.gcd,
        }
        expression = (expression or "").strip()
        if not expression:
            return "Error: empty expression."
        if len(expression) > 200:
            return "Error: expression too long."
        # Block dangerous patterns
        if any(kw in expression for kw in ["import", "exec", "eval", "open", "__", "os.", "sys."]):
            return "Error: disallowed keyword in expression."
        try:
            result = eval(expression, allowed, allowed)
            # Format nicely
            if isinstance(result, float) and result == int(result) and abs(result) < 1e15:
                return str(int(result))
            return str(result)
        except ZeroDivisionError:
            return "Error: division by zero."
        except Exception as e:
            return f"Error: {e}"
