"""
Example Plugin — Hello World greeter.
=======================================
Drop this file into the plugins/ directory and it will be auto-discovered.
"""

from Jarvis.core.plugins.base import JarvisPlugin, PluginMeta
from typing import Optional


class HelloPlugin(JarvisPlugin):
    META = PluginMeta(
        name="hello_world",
        version="1.0.0",
        author="Pathixo",
        description="A simple example plugin that responds to greetings.",
        tags=["example", "greeting"],
    )

    def on_load(self):
        print("[HelloPlugin] Loaded!")

    def on_enable(self):
        print("[HelloPlugin] Enabled!")

    def on_command(self, command: str) -> Optional[str]:
        if command.strip().lower() in ("hello", "hi", "hey"):
            return "Hello from the example plugin! 👋"
        return None
