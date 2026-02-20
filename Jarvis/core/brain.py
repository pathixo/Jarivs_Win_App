import requests
from Jarvis.config import OLLAMA_URL, OLLAMA_MODEL


DEFAULT_SYSTEM_PROMPT = (
    "You are Jarvis, a helpful AI assistant. "
    "You can access the file system using specific commands. "
    "If the user asks to create, read, or list files, respond with the exact command syntax below:\n"
    "- To list files: 'list files [directory]'\n"
    "- To read a file: 'read file [filename]'\n"
    "- To create a file: 'create file [filename] with content [content]'\n"
    "Do not wrap these commands in markdown or extra text if you want them executed directly. "
    "Otherwise, just chat normally."
)

class Brain:
    def __init__(self):
        self.output_buffer = ""
        self.ollama_url = OLLAMA_URL
        self.model = OLLAMA_MODEL
        self.timeout = 30
        self.system_prompt = DEFAULT_SYSTEM_PROMPT
        self.temperature = 0.7
        self.top_p = 0.9
        self.max_tokens = 256
        print(f"Brain initialized with Local LLM: {self.model} at {self.ollama_url}")

    def generate_response(self, text, history=None):
        """
        Generates response using Ollama API.
        Current implementation is synchronous and non-streaming for simplicity.
        """
        payload = {
            "model": self.model,
            "prompt": text,
            "system": self.system_prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "num_predict": self.max_tokens,
            },
        }
        
        try:
            response = requests.post(self.ollama_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            return data.get("response", "")
            
        except requests.exceptions.ConnectionError:
            return "Error: Could not connect to Local Brain (Ollama). Is it running?"
        except Exception as e:
            return f"Brain Error: {str(e)}"

    def set_model(self, model_name):
        model_name = (model_name or "").strip()
        if not model_name:
            return False, "Model name cannot be empty."
        self.model = model_name
        return True, f"LLM model set to '{self.model}'."

    def set_option(self, option_name, raw_value):
        name = option_name.lower().strip()
        try:
            if name == "temperature":
                value = float(raw_value)
                if value < 0 or value > 2:
                    return False, "temperature must be between 0 and 2."
                self.temperature = value
                return True, f"temperature set to {self.temperature}."

            if name == "top_p":
                value = float(raw_value)
                if value <= 0 or value > 1:
                    return False, "top_p must be > 0 and <= 1."
                self.top_p = value
                return True, f"top_p set to {self.top_p}."

            if name == "max_tokens":
                value = int(raw_value)
                if value <= 0:
                    return False, "max_tokens must be a positive integer."
                self.max_tokens = value
                return True, f"max_tokens set to {self.max_tokens}."

            if name == "timeout":
                value = int(raw_value)
                if value <= 0:
                    return False, "timeout must be a positive integer (seconds)."
                self.timeout = value
                return True, f"timeout set to {self.timeout}s."

            return False, f"Unknown option '{option_name}'."
        except ValueError:
            return False, f"Invalid value '{raw_value}' for {option_name}."

    def set_system_prompt(self, prompt):
        prompt = (prompt or "").strip()
        if not prompt:
            return False, "System prompt cannot be empty."
        self.system_prompt = prompt
        return True, "System prompt updated."

    def reset_settings(self):
        self.model = OLLAMA_MODEL
        self.timeout = 30
        self.temperature = 0.7
        self.top_p = 0.9
        self.max_tokens = 256
        self.system_prompt = DEFAULT_SYSTEM_PROMPT
        return "LLM settings reset to defaults."

    def get_status(self):
        return {
            "url": self.ollama_url,
            "model": self.model,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "system_prompt_preview": self.system_prompt[:120],
        }

    def list_local_models(self):
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=5)
            response.raise_for_status()
            data = response.json()
            models = data.get("models", [])
            names = [item.get("name") for item in models if item.get("name")]
            if not names:
                return True, []
            return True, names
        except Exception as e:
            return False, f"Could not fetch local models: {str(e)}"

    def execute_tool(self, tool_call):
        pass
