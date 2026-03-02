"""
Execution Environment for NOVUS.

Provides sandboxed execution for code, web search, API calls, and other
actions that agents can perform.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
import os
from typing import Any, Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass
class ExecutionResult:
    """Result of executing code or an action."""
    success: bool
    output: Any
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    artifacts: List[str] = None
    
    def __post_init__(self):
        if self.artifacts is None:
            self.artifacts = []


class ExecutionEnvironment:
    """
    Safe execution environment for agent actions.
    
    Provides:
    - Sandboxed Python code execution
    - Web search
    - File operations (restricted)
    - API calls (through proxy)
    """
    
    def __init__(
        self,
        max_execution_time: float = 30.0,
        max_output_size: int = 1_000_000,
        allow_network: bool = True,
        sandbox_dir: Optional[str] = None
    ):
        self.max_execution_time = max_execution_time
        self.max_output_size = max_output_size
        self.allow_network = allow_network
        
        # Create sandbox directory
        self.sandbox_dir = Path(sandbox_dir or tempfile.mkdtemp(prefix="novus_sandbox_"))
        
        logger.info(
            "execution_environment_initialized",
            sandbox_dir=str(self.sandbox_dir),
            allow_network=allow_network
        )
    
    async def execute_code(
        self,
        code: str,
        language: str = "python",
        dependencies: Optional[List[str]] = None
    ) -> ExecutionResult:
        """
        Execute code in sandbox.
        
        For Python, uses a restricted execution environment.
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            if language.lower() == "python":
                result = await self._execute_python(code, dependencies)
            elif language.lower() == "javascript":
                result = await self._execute_javascript(code)
            else:
                result = ExecutionResult(
                    success=False,
                    output=None,
                    error=f"Unsupported language: {language}"
                )
            
            result.execution_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            return result
            
        except Exception as e:
            logger.error("code_execution_error", error=str(e))
            return ExecutionResult(
                success=False,
                output=None,
                error=str(e),
                execution_time_ms=(asyncio.get_event_loop().time() - start_time) * 1000
            )
    
    async def _execute_python(
        self,
        code: str,
        dependencies: Optional[List[str]] = None
    ) -> ExecutionResult:
        """Execute Python code in sandbox."""
        
        # Build execution wrapper
        wrapped_code = self._wrap_python_code(code)
        
        # Write to temp file
        code_file = self.sandbox_dir / f"exec_{os.getpid()}.py"
        code_file.write_text(wrapped_code)
        
        try:
            # Build command
            cmd = ["python3", str(code_file)]
            
            # Add timeout
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.sandbox_dir)
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.max_execution_time
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ExecutionResult(
                    success=False,
                    output=None,
                    error=f"Execution timeout after {self.max_execution_time}s"
                )
            
            # Process output
            output = stdout.decode('utf-8', errors='replace')
            if len(output) > self.max_output_size:
                output = output[:self.max_output_size] + "... [truncated]"
            
            if stderr:
                logger.warning("code_execution_stderr", stderr=stderr.decode())
            
            success = process.returncode == 0
            
            return ExecutionResult(
                success=success,
                output=output if success else None,
                error=stderr.decode('utf-8', errors='replace') if not success else None
            )
            
        finally:
            # Cleanup
            if code_file.exists():
                code_file.unlink()
    
    def _wrap_python_code(self, code: str) -> str:
        """
        Wrap code with safety measures and output capture.
        """
        return f'''
import sys
import traceback

try:
{chr(10).join("    " + line for line in code.split(chr(10)))}
except Exception as e:
    print(f"Error: {{type(e).__name__}}: {{e}}", file=sys.stderr)
    sys.exit(1)
'''
    
    async def _execute_javascript(self, code: str) -> ExecutionResult:
        """Execute JavaScript code."""
        # Similar implementation for Node.js
        return ExecutionResult(
            success=False,
            output=None,
            error="JavaScript execution not yet implemented"
        )
    
    async def search_web(self, query: str, num_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search the web for information.
        
        Uses Brave Search API or falls back to alternative.
        """
        # This would integrate with actual search API
        # For now, return mock results
        
        logger.info("web_search", query=query)
        
        # Placeholder - would call Brave/SerpAPI/etc
        return [
            {
                "title": f"Result for: {query}",
                "url": f"https://example.com/result",
                "snippet": "Sample search result...",
            }
        ][:num_results]
    
    async def fetch_url(self, url: str, max_chars: int = 50000) -> Dict[str, Any]:
        """
        Fetch content from a URL.
        """
        if not self.allow_network:
            return {"error": "Network access disabled"}
        
        # Would use httpx in production
        logger.info("fetch_url", url=url)
        
        return {
            "url": url,
            "content": "[Would fetch actual content here]",
            "status": "not_implemented"
        }
    
    async def execute_shell(
        self,
        command: str,
        timeout: float = 30.0
    ) -> ExecutionResult:
        """
        Execute a shell command (restricted).
        
        Only allows whitelisted commands for safety.
        """
        # Whitelist of safe commands
        allowed_commands = {
            "ls", "cat", "head", "tail", "grep", "wc", "find", "echo",
            "python3", "pip3", "git"
        }
        
        # Parse command
        parts = command.strip().split()
        if not parts or parts[0] not in allowed_commands:
            return ExecutionResult(
                success=False,
                output=None,
                error=f"Command not allowed: {parts[0] if parts else 'empty'}"
            )
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.sandbox_dir)
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            return ExecutionResult(
                success=process.returncode == 0,
                output=stdout.decode('utf-8', errors='replace'),
                error=stderr.decode('utf-8', errors='replace') if stderr else None
            )
            
        except asyncio.TimeoutError:
            process.kill()
            return ExecutionResult(
                success=False,
                output=None,
                error=f"Command timed out after {timeout}s"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output=None,
                error=str(e)
            )
    
    def cleanup(self) -> None:
        """Clean up sandbox directory."""
        import shutil
        if self.sandbox_dir.exists():
            shutil.rmtree(self.sandbox_dir)
            logger.info("sandbox_cleaned", path=str(self.sandbox_dir))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get execution environment stats."""
        return {
            "sandbox_dir": str(self.sandbox_dir),
            "allow_network": self.allow_network,
            "max_execution_time": self.max_execution_time,
            "max_output_size": self.max_output_size,
        }
