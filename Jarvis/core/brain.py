
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
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": text,
            "stream": False,
            # "context": history # Ollama uses 'context' for history (list of ints), or 'messages' for chat format
        }
        
        # If we want chat history, we should likely use the /api/chat endpoint instead of /api/generate
        # But for now, complying with original interface "text" input
        
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
