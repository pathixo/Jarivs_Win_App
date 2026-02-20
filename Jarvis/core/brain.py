
import requests
import json
from Jarvis.config import OLLAMA_URL, OLLAMA_MODEL

class Brain:
    def __init__(self):
        self.output_buffer = ""
        # We can ping Ollama to check if it's alive, but lazy check is fine too.
        print(f"Brain initialized with Local LLM: {OLLAMA_MODEL} at {OLLAMA_URL}")

    def generate_response(self, text, history=None):
        """
        Generates response using Ollama API.
        Current implementation is synchronous and non-streaming for simplicity.
        """
        system_prompt = (
            "You are Jarvis, a helpful AI assistant. "
            "You can access the file system using specific commands. "
            "If the user asks to create, read, or list files, respond with the exact command syntax below:\n"
            "- To list files: 'list files [directory]'\n"
            "- To read a file: 'read file [filename]'\n"
            "- To create a file: 'create file [filename] with content [content]'\n"
            "Do not wrap these commands in markdown or extra text if you want them executed directly. "
            "Otherwise, just chat normally."
        )

        payload = {
            "model": OLLAMA_MODEL,
            "prompt": text,
            "system": system_prompt,
            "stream": False,
        }
        
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            return data.get("response", "")
            
        except requests.exceptions.ConnectionError:
            return "Error: Could not connect to Local Brain (Ollama). Is it running?"
        except Exception as e:
            return f"Brain Error: {str(e)}"

    def execute_tool(self, tool_call):
        # Placeholder for tool execution logic
        pass
