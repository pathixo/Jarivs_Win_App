"""
Tools Module — Sandboxed File & Terminal Operations
=====================================================
Implements workspace-sandboxed file system and command operations.
Delegates all OS interactions through the SystemBackend abstraction.
"""

import math
import os
from typing import Optional

import ast
import operator


from Jarvis.core.system.backend import SystemBackend


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
        safe, abs_path = self._is_safe_path(directory)
        if not safe:
            return "Error: Access denied. Path is outside workspace."
            
        result = self.backend.list_dir(abs_path)
        if result.success:
            return result.output
        return f"Error listing files: {result.error}"
    
    def read_file(self, filepath):
        """
        Reads content of a text file (relative to workspace).
        """
        safe, abs_path = self._is_safe_path(filepath)
        if not safe:
            return "Error: Access denied. Path is outside workspace."

        result = self.backend.read_file(abs_path)
        if result.success:
            return result.output
        return f"Error reading file: {result.error}"

    def write_file(self, filepath, content):
        """
        Writes content to a file (relative to workspace). Overwrites if exists.
        """
        safe, abs_path = self._is_safe_path(filepath)
        if not safe:
            return "Error: Access denied. Path is outside workspace."

        result = self.backend.write_file(abs_path, content)
        if result.success:
            return f"File '{filepath}' written successfully."
        return f"Error writing file: {result.error}"
    def calculate(self, expression: str) -> str:
       
       #Secure mathematical expression evaluator using AST instead of eval().
        

       SAFE_OPERATORS = {
           ast.Add: operator.add,
           ast.Sub: operator.sub,
           ast.Mult: operator.mul,
           ast.Div: operator.truediv,
           ast.Pow: operator.pow,
           ast.Mod: operator.mod,
       }

       SAFE_FUNCTIONS = {
           "abs": abs,
           "round": round,
           "min": min,
           "max": max,
           "pow": pow,
           "sqrt": math.sqrt,
           "ceil": math.ceil,
           "floor": math.floor,
           "log": math.log,
           "log10": math.log10,
           "log2": math.log2,
           "sin": math.sin,
           "cos": math.cos,
           "tan": math.tan,
           "asin": math.asin,
           "acos": math.acos,
           "atan": math.atan,
           "degrees": math.degrees,
           "radians": math.radians,
           "factorial": math.factorial,
           "gcd": math.gcd,
       }

       expression = (expression or "").strip()

       if not expression:
           return "Error: empty expression."

       if len(expression) > 200:
           return "Error: expression too long."

       try:
           tree = ast.parse(expression, mode="eval")

           def _eval(node):

               if isinstance(node, ast.Expression):
                   return _eval(node.body)

               elif isinstance(node, ast.Constant):
                   if isinstance(node.value, (int, float)):
                       return node.value
                   raise ValueError("Only numbers allowed")

               elif isinstance(node, ast.BinOp):
                   if type(node.op) not in SAFE_OPERATORS:
                       raise ValueError("Operator not allowed")
                   return SAFE_OPERATORS[type(node.op)](
                       _eval(node.left), _eval(node.right)
                   )

               elif isinstance(node, ast.UnaryOp):
                   if isinstance(node.op, ast.USub):
                       return -_eval(node.operand)
                   raise ValueError("Unary operator not allowed")

               elif isinstance(node, ast.Call):
                   if not isinstance(node.func, ast.Name):
                       raise ValueError("Invalid function")

                   func = node.func.id
                   if func not in SAFE_FUNCTIONS:
                       raise ValueError(f"Function '{func}' not allowed")

                   args = [_eval(arg) for arg in node.args]
                   return SAFE_FUNCTIONS[func](*args)

               elif isinstance(node, ast.Name):
                   if node.id == "pi":
                       return math.pi
                   if node.id == "e":
                       return math.e
                   raise ValueError(f"Name '{node.id}' not allowed")

               else:
                   raise ValueError("Unsupported expression")

           result = _eval(tree)

           if isinstance(result, float) and result == int(result):
            return str(int(result))

           return str(result)

       except ZeroDivisionError:
           return "Error: division by zero."

       except Exception as e:
           return f"Error: invalid or unsafe expression ({e})"
    
    # from Jarvis.core.tools import Tools

