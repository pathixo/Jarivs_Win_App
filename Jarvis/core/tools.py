import subprocess
import os

class Tools:
    """
    Implements local tools for file system and terminal operations.
    Enforces sandboxing within the 'workspace' directory.
    """
    def __init__(self):
        # Define workspace directory relative to project root
        self.workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../workspace"))
        if not os.path.exists(self.workspace_dir):
            os.makedirs(self.workspace_dir)
            print(f"Created workspace directory at: {self.workspace_dir}")

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
        Executes a shell command and returns output.
        """
        try:
            # Run in workspace directory
            result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=self.workspace_dir)
            if result.returncode == 0:
                return f"Output:\n{result.stdout}"
            else:
                return f"Error:\n{result.stderr}"
        except Exception as e:
            return f"Error executing command: {str(e)}"
    
    def list_files(self, directory="."):
        """
        Lists files in the specified directory (relative to workspace).
        """
        safe, abs_path = self._is_safe_path(directory)
        if not safe:
            return "Error: Access denied. Path is outside workspace."
            
        try:
            files = os.listdir(abs_path)
            return "\n".join(files)
        except Exception as e:
            return f"Error listing files: {str(e)}"
    
    def read_file(self, filepath):
        """
        Reads content of a text file (relative to workspace).
        """
        safe, abs_path = self._is_safe_path(filepath)
        if not safe:
            return "Error: Access denied. Path is outside workspace."

        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def write_file(self, filepath, content):
        """
        Writes content to a file (relative to workspace). Overwrites if exists.
        """
        safe, abs_path = self._is_safe_path(filepath)
        if not safe:
            return "Error: Access denied. Path is outside workspace."

        try:
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"File '{filepath}' written successfully."
        except Exception as e:
            return f"Error writing file: {str(e)}"
