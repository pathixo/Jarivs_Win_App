"""
Coding Agent — Autonomous Code Generation & Debugging
======================================================
Specialized agent for programming tasks that can:

  1. Generate code based on user requirements
  2. Save code to workspace files
  3. Run code and capture output/errors
  4. Analyze errors and fix bugs
  5. Iterate until code works correctly

Architecture:
  - Inherits from the ReAct pattern but specialized for coding
  - Has access to workspace file system (sandboxed)
  - Can execute Python, Node.js, and shell scripts
  - Max iterations prevent infinite loops
  - Captures stderr for debugging
"""

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from enum import Enum

logger = logging.getLogger("jarvis.coding_agent")


# ─────────────────────── Code Execution Result ──────────────────────────────

@dataclass
class CodeExecutionResult:
    """Result of running code."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    runtime_ms: float = 0.0
    error_type: str = ""  # "syntax", "runtime", "timeout", "import"


@dataclass
class CodingStep:
    """A single step in the coding agent's workflow."""
    step_num: int
    action: str  # "generate", "run", "fix", "complete"
    code: str = ""
    filename: str = ""
    execution_result: Optional[CodeExecutionResult] = None
    thought: str = ""
    timestamp: float = 0.0


@dataclass
class CodingResult:
    """Final result from the coding agent."""
    task: str
    final_code: str
    filename: str
    steps: List[CodingStep] = field(default_factory=list)
    success: bool = False
    final_output: str = ""
    total_time: float = 0.0
    iterations: int = 0
    error: Optional[str] = None


# ─────────────────────── Coding Agent ───────────────────────────────────────

class CodingAgent:
    """
    Specialized agent for writing, running, and debugging code.
    
    Workflow:
      1. User describes what they want
      2. Agent generates initial code
      3. Agent saves and runs the code
      4. If errors: agent analyzes and fixes
      5. Repeat until working or max iterations
    """
    
    # Prompt for code generation
    CODE_GEN_PROMPT = """\
You are an expert programmer. Generate code to accomplish the user's task.

Rules:
1. Write clean, working code
2. Include all necessary imports
3. Add helpful comments
4. Handle common edge cases
5. Return ONLY the code, wrapped in ```python or appropriate language tags
6. If the task is unclear, make reasonable assumptions

Task: {task}

{context}
"""

    # Prompt for error fixing
    FIX_PROMPT = """\
The following code has an error. Analyze the error and fix the code.

Code ({language}):
```
{code}
```

Error output:
```
{error}
```

Provide the COMPLETE fixed code (not just the fix). Wrap in ```{language} tags.
Briefly explain what was wrong before the code block.
"""

    SUPPORTED_LANGUAGES = {
        "python": {"ext": ".py", "cmd": "python", "timeout": 30},
        "javascript": {"ext": ".js", "cmd": "node", "timeout": 30},
        "typescript": {"ext": ".ts", "cmd": "npx ts-node", "timeout": 45},
        "shell": {"ext": ".sh", "cmd": "bash", "timeout": 30},
        "batch": {"ext": ".bat", "cmd": "cmd /c", "timeout": 30},
        "powershell": {"ext": ".ps1", "cmd": "powershell -File", "timeout": 30},
    }

    def __init__(
        self,
        brain,  # Brain instance for LLM calls
        workspace_dir: str = None,
        max_iterations: int = 5,
        timeout_per_run: float = 30.0,
    ):
        """
        Initialize the coding agent.
        
        Args:
            brain: Brain instance for code generation
            workspace_dir: Directory for saving code files
            max_iterations: Max fix attempts before giving up
            timeout_per_run: Timeout for each code execution
        """
        self.brain = brain
        self.workspace_dir = workspace_dir or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../workspace")
        )
        self.max_iterations = max_iterations
        self.timeout_per_run = timeout_per_run
        
        # Ensure workspace exists
        os.makedirs(self.workspace_dir, exist_ok=True)
    
    def run(
        self,
        task: str,
        language: str = "python",
        filename: str = None,
        status_callback: Optional[Callable[[str, str], None]] = None,
    ) -> CodingResult:
        """
        Run the coding agent to complete a programming task.
        
        Args:
            task: Description of what the code should do
            language: Programming language (python, javascript, etc.)
            filename: Optional filename (auto-generated if not provided)
            status_callback: Optional callback(action, message) for progress
            
        Returns:
            CodingResult with the final code and execution history
        """
        start_time = time.time()
        steps: List[CodingStep] = []
        
        # Normalize language
        language = language.lower()
        if language not in self.SUPPORTED_LANGUAGES:
            language = "python"  # Default
        
        lang_config = self.SUPPORTED_LANGUAGES[language]
        
        # Generate filename if not provided
        if not filename:
            timestamp = int(time.time())
            filename = f"code_{timestamp}{lang_config['ext']}"
        elif not filename.endswith(lang_config['ext']):
            filename += lang_config['ext']
        
        filepath = os.path.join(self.workspace_dir, filename)
        
        # ── Step 1: Generate initial code ─────────────────────────────
        if status_callback:
            status_callback("generate", "Generating code...")
        
        step = CodingStep(
            step_num=1,
            action="generate",
            filename=filename,
            timestamp=time.time(),
        )
        
        code = self._generate_code(task, language)
        step.code = code
        
        if not code:
            return CodingResult(
                task=task,
                final_code="",
                filename=filename,
                steps=steps,
                success=False,
                error="Failed to generate code",
                total_time=time.time() - start_time,
            )
        
        steps.append(step)
        
        # ── Step 2-N: Run → Fix loop ──────────────────────────────────
        current_code = code
        
        for iteration in range(self.max_iterations):
            if status_callback:
                status_callback("run", f"Running code (attempt {iteration + 1})...")
            
            # Save and run
            self._save_code(filepath, current_code)
            exec_result = self._execute_code(filepath, language)
            
            run_step = CodingStep(
                step_num=len(steps) + 1,
                action="run",
                code=current_code,
                filename=filename,
                execution_result=exec_result,
                timestamp=time.time(),
            )
            steps.append(run_step)
            
            # Check if successful
            if exec_result.success:
                if status_callback:
                    status_callback("complete", "Code executed successfully!")
                
                return CodingResult(
                    task=task,
                    final_code=current_code,
                    filename=filename,
                    steps=steps,
                    success=True,
                    final_output=exec_result.stdout,
                    total_time=time.time() - start_time,
                    iterations=iteration + 1,
                )
            
            # ── Fix the code ──────────────────────────────────────────
            if iteration < self.max_iterations - 1:
                if status_callback:
                    status_callback("fix", f"Fixing error: {exec_result.error_type}")
                
                fix_step = CodingStep(
                    step_num=len(steps) + 1,
                    action="fix",
                    timestamp=time.time(),
                )
                
                error_text = exec_result.stderr or exec_result.stdout
                fixed_code = self._fix_code(current_code, error_text, language)
                
                fix_step.code = fixed_code
                fix_step.thought = f"Attempting to fix {exec_result.error_type} error"
                steps.append(fix_step)
                
                if fixed_code and fixed_code != current_code:
                    current_code = fixed_code
                else:
                    # No meaningful fix generated
                    break
        
        # Max iterations reached - return best effort
        return CodingResult(
            task=task,
            final_code=current_code,
            filename=filename,
            steps=steps,
            success=False,
            final_output=exec_result.stderr if exec_result else "",
            total_time=time.time() - start_time,
            iterations=len([s for s in steps if s.action == "run"]),
            error=f"Could not fix code after {self.max_iterations} attempts",
        )
    
    def _generate_code(self, task: str, language: str) -> str:
        """Generate initial code using the LLM."""
        try:
            prompt = self.CODE_GEN_PROMPT.format(
                task=task,
                context=f"Language: {language}\nWrite complete, runnable code.",
            )
            
            response = self.brain.generate_response(
                prompt,
                skip_memory=True,
            )
            
            return self._extract_code(response, language)
            
        except Exception as e:
            logger.error(f"Code generation failed: {e}")
            return ""
    
    def _fix_code(self, code: str, error: str, language: str) -> str:
        """Ask the LLM to fix the code based on the error."""
        try:
            prompt = self.FIX_PROMPT.format(
                language=language,
                code=code,
                error=error[:2000],  # Limit error length
            )
            
            response = self.brain.generate_response(
                prompt,
                skip_memory=True,
            )
            
            return self._extract_code(response, language)
            
        except Exception as e:
            logger.error(f"Code fix failed: {e}")
            return code  # Return original if fix fails
    
    def _extract_code(self, response: str, language: str) -> str:
        """Extract code from a response with markdown code blocks."""
        # Try language-specific block first
        patterns = [
            rf"```{language}\n(.*?)```",
            rf"```{language.lower()}\n(.*?)```",
            r"```\n(.*?)```",
            r"```(.*?)```",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # No code block found - return the whole response cleaned up
        lines = response.strip().split('\n')
        # Remove markdown formatting
        clean_lines = [l for l in lines if not l.startswith('```')]
        return '\n'.join(clean_lines)
    
    def _save_code(self, filepath: str, code: str):
        """Save code to a file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(code)
    
    def _execute_code(self, filepath: str, language: str) -> CodeExecutionResult:
        """Execute code and capture output."""
        lang_config = self.SUPPORTED_LANGUAGES.get(language, self.SUPPORTED_LANGUAGES["python"])
        
        # Build command
        cmd = f"{lang_config['cmd']} \"{filepath}\""
        
        start_time = time.time()
        
        try:
            # Run in workspace directory
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=lang_config['timeout'],
                cwd=self.workspace_dir,
            )
            
            runtime_ms = (time.time() - start_time) * 1000
            
            # Determine error type
            error_type = ""
            if result.returncode != 0:
                stderr = result.stderr.lower()
                if "syntaxerror" in stderr or "syntax error" in stderr:
                    error_type = "syntax"
                elif "importerror" in stderr or "modulenotfounderror" in stderr:
                    error_type = "import"
                elif "nameerror" in stderr or "attributeerror" in stderr:
                    error_type = "reference"
                elif "typeerror" in stderr:
                    error_type = "type"
                else:
                    error_type = "runtime"
            
            return CodeExecutionResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                runtime_ms=runtime_ms,
                error_type=error_type,
            )
            
        except subprocess.TimeoutExpired:
            return CodeExecutionResult(
                success=False,
                stderr=f"Code execution timed out after {lang_config['timeout']}s",
                exit_code=-1,
                runtime_ms=(time.time() - start_time) * 1000,
                error_type="timeout",
            )
        except Exception as e:
            return CodeExecutionResult(
                success=False,
                stderr=str(e),
                exit_code=-1,
                runtime_ms=(time.time() - start_time) * 1000,
                error_type="runtime",
            )


# ─────────────────────── Convenience Function ───────────────────────────────

def code_task(
    task: str,
    brain,
    language: str = "python",
    **kwargs
) -> CodingResult:
    """
    Convenience function to run a coding task.
    
    Args:
        task: Description of what the code should do
        brain: Brain instance
        language: Programming language
        **kwargs: Additional args for CodingAgent
        
    Returns:
        CodingResult
    """
    agent = CodingAgent(brain=brain, **kwargs)
    return agent.run(task, language=language)
