import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class TerminalTool:
    """
    Tool that allows the agent to execute terminal/shell commands
    inside the sandbox.
    """
    def __init__(self, sandbox_manager):
        # We pass the SandboxManager instance so we can run commands inside the microVM
        self.sandbox_manager = sandbox_manager

    def run(self, command: str, workdir: str = None) -> Dict[str, Any]:
        """
        Executes a shell command in the E2B sandbox and returns outputs.
        
        Args:
            command: The shell command string to execute.
            workdir: Optional sub-directory path to run the command in.
        """
        try:
            logger.info(f"Running terminal command: {command}")
            # Delegate command execution to our SandboxManager
            res = self.sandbox_manager.execute_command(command, workdir=workdir)
            return {
                "exit_code": res["exit_code"],
                "stdout": res["stdout"],
                "stderr": res["stderr"]
            }
        except Exception as e:
            logger.error(f"Error running command '{command}': {e}")
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Error executing command: {str(e)}"
            }
