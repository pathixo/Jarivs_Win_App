
import subprocess
import os

class Tools:
    """
    Implements local tools for file system and terminal operations.
    """
    def execute_terminal_command(self, command):
        """
        Executes a shell command and returns output.
        """
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                return f"Output:\n{result.stdout}"
            else:
                return f"Error:\n{result.stderr}"
        except Exception as e:
            return f"Error executing command: {str(e)}"
    
    def list_files(self, directory="."):
        """
        Lists files in the specified directory.
        """
        try:
            files = os.listdir(directory)
            return "\n".join(files)
        except Exception as e:
            return f"Error listing files: {str(e)}"
    
    def read_file(self, filepath):
        """
        Reads content of a text file.
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def write_file(self, filepath, content):
        """
        Writes content to a file. Overwrites if exists.
        """
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"File '{filepath}' written successfully."
        except Exception as e:
            return f"Error writing file: {str(e)}"
