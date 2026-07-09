import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class RipgrepTool:
    """
    Tool that allows the agent to search for patterns across the codebase
    using ripgrep (rg) inside the sandbox.
    """
    def __init__(self, sandbox_manager):
        self.sandbox_manager = sandbox_manager

    def search(self, query: str, file_pattern: str = None) -> Dict[str, Any]:
        """
        Searches the codebase for a text query.
        
        Args:
            query: The search term or pattern.
            file_pattern: Optional glob pattern to filter files (e.g. "*.py").
        """
        # Escape query string quotes
        safe_query = query.replace("'", "'\\''")
        
        # Build the ripgrep command
        # -n: line numbers, -H: show filenames, --no-heading: single-line output
        cmd = f"rg -n -H --no-heading '{safe_query}'"
        if file_pattern:
            cmd += f" -g '{file_pattern}'"
            
        logger.info(f"Running ripgrep search in sandbox: {cmd}")
        res = self.sandbox_manager.execute_command(cmd)
        
        # If ripgrep is not installed (shell exit code 127), fall back to standard grep
        if res["exit_code"] == 127:
            logger.info("ripgrep not found in sandbox, falling back to standard grep")
            # -r: recursive, -n: line numbers, -I: ignore binary files
            fallback_cmd = f"grep -rnI '{safe_query}' ."
            res = self.sandbox_manager.execute_command(fallback_cmd)
            
        return {
            "exit_code": res["exit_code"],
            "stdout": res["stdout"],
            "stderr": res["stderr"]
        }
