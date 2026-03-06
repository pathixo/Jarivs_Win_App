"""
ReAct Agent — Autonomous Multi-Step Task Execution
===================================================
Implements the ReAct (Reasoning + Acting) pattern for complex,
multi-step tasks that require planning and tool use.

Architecture:
  1. User requests a complex task
  2. Agent thinks about what to do (Thought)
  3. Agent selects and calls a tool (Action)
  4. Agent receives tool output (Observation)
  5. Loop until task is complete or max iterations reached

Features:
  - Tool registry with automatic prompt generation
  - Configurable max iterations and timeouts
  - Execution trace for debugging
  - Safety guards and sandboxing
  - Integration with existing Tools + WebSearch modules
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger("jarvis.agent")


# ─────────────────────── Tool Definition ────────────────────────────────────

class ToolRegistry:
    """
    Registry of available tools for the ReAct agent.
    Each tool has a name, description, and callable implementation.
    """
    
    def __init__(self):
        self._tools: Dict[str, "Tool"] = {}
    
    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, str],
        func: Callable[..., str],
    ):
        """
        Register a tool.
        
        Args:
            name: Tool name (snake_case, e.g. "web_search")
            description: What the tool does
            parameters: Dict of param_name -> param_description
            func: The callable that executes the tool
        """
        self._tools[name] = Tool(
            name=name,
            description=description,
            parameters=parameters,
            func=func,
        )
    
    def get(self, name: str) -> Optional["Tool"]:
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        return list(self._tools.keys())
    
    def to_prompt_string(self) -> str:
        """Generate a formatted tool list for the LLM prompt."""
        lines = ["Available tools:"]
        for name, tool in self._tools.items():
            params_str = ", ".join(f"{k}: {v}" for k, v in tool.parameters.items())
            lines.append(f"  - {name}({params_str}): {tool.description}")
        return "\n".join(lines)


@dataclass
class Tool:
    """A registered tool."""
    name: str
    description: str
    parameters: Dict[str, str]
    func: Callable[..., str]
    
    def execute(self, **kwargs) -> str:
        """Execute the tool with given parameters."""
        try:
            return self.func(**kwargs)
        except Exception as e:
            return f"Error executing {self.name}: {e}"


# ─────────────────────── Agent State ────────────────────────────────────────

class AgentStatus(Enum):
    THINKING = "thinking"
    ACTING = "acting"
    OBSERVING = "observing"
    COMPLETE = "complete"
    ERROR = "error"
    MAX_ITERATIONS = "max_iterations"


@dataclass
class AgentStep:
    """A single step in the agent's execution trace."""
    step_num: int
    thought: str = ""
    action: str = ""
    action_input: Dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    timestamp: float = 0.0


@dataclass
class AgentResult:
    """Result of an agent execution run."""
    task: str
    final_answer: str
    steps: List[AgentStep] = field(default_factory=list)
    status: AgentStatus = AgentStatus.COMPLETE
    total_time: float = 0.0
    error: Optional[str] = None


# ─────────────────────── ReAct Agent ────────────────────────────────────────

class ReActAgent:
    """
    ReAct Agent for autonomous multi-step task execution.
    
    Uses the Thought → Action → Observation loop to solve complex tasks.
    """
    
    # Prompt template for the ReAct loop
    SYSTEM_PROMPT = """\
You are a helpful AI assistant that can use tools to accomplish tasks.
For each task, think step by step and use tools when needed.

{tools_description}

Response format (use EXACTLY this format):
Thought: <your reasoning about what to do next>
Action: <tool_name>
Action Input: {{"param1": "value1", "param2": "value2"}}

OR if you have enough information to answer:
Thought: <your final reasoning>
Final Answer: <your complete answer to the user's question>

Rules:
1. Always start with a Thought
2. If you need more information, use a tool
3. After observing tool output, think again
4. When you have enough info, give Final Answer
5. Be concise in your thoughts
6. Never make up information - use tools to verify
"""

    def __init__(
        self,
        brain,  # The Brain instance for LLM calls
        tools_instance=None,  # The Tools instance for file/shell ops
        action_router=None,   # ActionRouter for sandboxed shell execution
        max_iterations: int = 10,
        timeout: float = 120.0,
    ):
        """
        Initialize the ReAct agent.
        
        Args:
            brain: Brain instance for LLM calls
            tools_instance: Tools instance for file/shell operations
            action_router: ActionRouter instance — required to enable the
                           run_command tool.  All shell commands are routed
                           through ActionRouter.execute_shell() so the full
                           3-Tier Sandbox (SafetyEngine) is always applied.
                           If None, the run_command tool is NOT registered
                           (fail-safe: no shell access without the safety gate).
            max_iterations: Maximum think-act-observe cycles
            timeout: Maximum total execution time in seconds
        """
        self.brain = brain
        self.tools_instance = tools_instance
        self.action_router = action_router
        self.max_iterations = max_iterations
        self.timeout = timeout
        
        # Initialize tool registry
        self.registry = ToolRegistry()
        self._register_default_tools()
    
    def _register_default_tools(self):
        """Register the default set of tools."""
        # Web search
        from Jarvis.core.web_search import web_search, format_search_results
        self.registry.register(
            name="web_search",
            description="Search the web for information. Returns search results with snippets.",
            parameters={"query": "The search query string"},
            func=lambda query: format_search_results(web_search(query, max_results=5), include_urls=True),
        )
        
        # Calculator
        if self.tools_instance:
            self.registry.register(
                name="calculate",
                description="Evaluate a mathematical expression. Supports +, -, *, /, **, sqrt, sin, cos, etc.",
                parameters={"expression": "Mathematical expression to evaluate"},
                func=self.tools_instance.calculate,
            )
            
            # File operations (sandboxed to workspace)
            self.registry.register(
                name="read_file",
                description="Read the contents of a file in the workspace directory.",
                parameters={"filepath": "Path to file (relative to workspace)"},
                func=self.tools_instance.read_file,
            )
            
            self.registry.register(
                name="write_file",
                description="Write content to a file in the workspace directory.",
                parameters={"filepath": "Path to file", "content": "Content to write"},
                func=self.tools_instance.write_file,
            )
            
            self.registry.register(
                name="list_files",
                description="List files in a directory within the workspace.",
                parameters={"directory": "Directory path (relative to workspace, default '.')"},
                func=self.tools_instance.list_files,
            )
            
            # run_command is only registered when an ActionRouter is available.
            # All commands are routed through ActionRouter.execute_shell() so
            # the full 3-Tier Sandbox (SafetyEngine) is enforced:
            #   RED  (CRITICAL) → always blocked
            #   YELLOW (HIGH/MEDIUM) → requires user confirmation
            #   GREEN  (LOW)    → executes directly
            # Bypassing this gate (e.g. via tools_instance.execute_terminal_command)
            # would skip safety checks entirely — never do that here.
            if self.action_router is not None:
                def _sandboxed_run_command(command: str) -> str:
                    result = self.action_router.execute_shell(command, from_llm=True)
                    if result.success:
                        return f"Output:\n{result.stdout}" if result.stdout else "Command executed."
                    return f"Error:\n{result.error}" if result.error else f"Error:\n{result.message}"

                self.registry.register(
                    name="run_command",
                    description="Execute a shell command. Use for system tasks, running scripts, etc.",
                    parameters={"command": "The shell command to execute"},
                    func=_sandboxed_run_command,
                )
    
    def run(
        self,
        task: str,
        status_callback: Optional[Callable[[AgentStatus, str], None]] = None,
    ) -> AgentResult:
        """
        Run the agent to complete a task.
        
        Args:
            task: The task description / user request
            status_callback: Optional callback(status, message) for progress updates
            
        Returns:
            AgentResult with the execution trace and final answer
        """
        start_time = time.time()
        steps: List[AgentStep] = []
        
        # Build the system prompt with tools
        system_prompt = self.SYSTEM_PROMPT.format(
            tools_description=self.registry.to_prompt_string()
        )
        
        # Initialize conversation for the agent
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Task: {task}"},
        ]
        
        for iteration in range(self.max_iterations):
            # Check timeout
            if time.time() - start_time > self.timeout:
                return AgentResult(
                    task=task,
                    final_answer="Task timed out. Here's what I found so far: " + 
                                 (steps[-1].observation if steps else "No results yet."),
                    steps=steps,
                    status=AgentStatus.MAX_ITERATIONS,
                    total_time=time.time() - start_time,
                )
            
            step = AgentStep(step_num=iteration + 1, timestamp=time.time())
            
            if status_callback:
                status_callback(AgentStatus.THINKING, f"Step {iteration + 1}: Thinking...")
            
            # Get LLM response
            try:
                response = self.brain.generate_response(
                    messages[-1]["content"] if messages[-1]["role"] == "user" else 
                    f"Continue from observation: {messages[-1]['content']}",
                    history=messages[:-1],
                    skip_memory=True,  # Don't pollute main conversation
                )
            except Exception as e:
                logger.error(f"Agent LLM error: {e}")
                return AgentResult(
                    task=task,
                    final_answer=f"I encountered an error: {e}",
                    steps=steps,
                    status=AgentStatus.ERROR,
                    total_time=time.time() - start_time,
                    error=str(e),
                )
            
            # Parse the response
            thought, action, action_input, final_answer = self._parse_response(response)
            step.thought = thought
            
            # Check for final answer
            if final_answer:
                step.observation = "Task complete."
                steps.append(step)
                return AgentResult(
                    task=task,
                    final_answer=final_answer,
                    steps=steps,
                    status=AgentStatus.COMPLETE,
                    total_time=time.time() - start_time,
                )
            
            # Execute action
            if action:
                step.action = action
                step.action_input = action_input
                
                if status_callback:
                    status_callback(AgentStatus.ACTING, f"Using tool: {action}")
                
                tool = self.registry.get(action)
                if tool:
                    try:
                        observation = tool.execute(**action_input)
                    except Exception as e:
                        observation = f"Tool error: {e}"
                else:
                    observation = f"Unknown tool: {action}. Available: {', '.join(self.registry.list_tools())}"
                
                step.observation = observation
                
                # Add to conversation history
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Observation: {observation}"})
                
                if status_callback:
                    status_callback(AgentStatus.OBSERVING, f"Observed: {observation[:100]}...")
            else:
                # No action and no final answer - nudge the model
                step.observation = "No action taken. Please use a tool or provide a final answer."
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": "Please continue with the task. Use a tool or provide your final answer."})
            
            steps.append(step)
        
        # Max iterations reached
        return AgentResult(
            task=task,
            final_answer="I reached the maximum number of steps. Here's what I found: " +
                         (steps[-1].observation if steps else "No results."),
            steps=steps,
            status=AgentStatus.MAX_ITERATIONS,
            total_time=time.time() - start_time,
        )
    
    def _parse_response(self, response: str) -> tuple:
        """
        Parse the LLM response into thought, action, action_input, final_answer.
        
        Returns:
            (thought, action, action_input, final_answer)
        """
        thought = ""
        action = ""
        action_input = {}
        final_answer = ""
        
        # Extract Thought
        thought_match = re.search(r"Thought:\s*(.+?)(?=Action:|Final Answer:|$)", response, re.DOTALL | re.IGNORECASE)
        if thought_match:
            thought = thought_match.group(1).strip()
        
        # Check for Final Answer first
        final_match = re.search(r"Final Answer:\s*(.+?)$", response, re.DOTALL | re.IGNORECASE)
        if final_match:
            final_answer = final_match.group(1).strip()
            return thought, action, action_input, final_answer
        
        # Extract Action
        action_match = re.search(r"Action:\s*(\w+)", response, re.IGNORECASE)
        if action_match:
            action = action_match.group(1).strip()
        
        # Extract Action Input (JSON)
        input_match = re.search(r"Action Input:\s*(\{.+?\})", response, re.DOTALL | re.IGNORECASE)
        if input_match:
            try:
                action_input = json.loads(input_match.group(1))
            except json.JSONDecodeError:
                # Try to extract key-value pairs manually
                action_input = self._parse_loose_json(input_match.group(1))
        
        return thought, action, action_input, final_answer
    
    def _parse_loose_json(self, text: str) -> Dict[str, Any]:
        """Try to parse loosely formatted JSON-like text."""
        result = {}
        # Match "key": "value" or "key": value patterns
        pairs = re.findall(r'"?(\w+)"?\s*:\s*"?([^",}]+)"?', text)
        for key, value in pairs:
            result[key] = value.strip()
        return result


# ─────────────────────── Convenience Function ───────────────────────────────

def run_agent_task(task: str, brain, tools=None, **kwargs) -> AgentResult:
    """
    Convenience function to run a task with the ReAct agent.
    
    Args:
        task: Task description
        brain: Brain instance
        tools: Tools instance (optional)
        **kwargs: Additional args for ReActAgent
        
    Returns:
        AgentResult
    """
    agent = ReActAgent(brain=brain, tools_instance=tools, **kwargs)
    return agent.run(task)
