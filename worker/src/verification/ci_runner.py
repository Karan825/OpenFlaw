import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class CIRunner:
    """
    Handles installation of dependencies and execution of test suites
    inside the E2B sandbox to verify agent modifications.
    """
    def __init__(self, sandbox_manager, language: str, package_manager: str):
        self.sandbox_manager = sandbox_manager
        self.language = language
        self.package_manager = package_manager

    def install_dependencies(self) -> Dict[str, Any]:
        """Runs the installation command for the detected package manager."""
        from sandbox.inference import get_default_commands
        cmds = get_default_commands(self.language, self.package_manager)
        install_cmd = cmds.get("install")
        
        if not install_cmd:
            logger.info("No install command specified for this environment.")
            return {"success": True, "exit_code": 0, "stdout": "No installation required.", "stderr": ""}
            
        logger.info(f"Installing dependencies using command: {install_cmd}")
        res = self.sandbox_manager.execute_command(install_cmd)
        return {
            "success": res["exit_code"] == 0,
            "exit_code": res["exit_code"],
            "stdout": res["stdout"],
            "stderr": res["stderr"]
        }

    def run_tests(self) -> Dict[str, Any]:
        """Runs the test suite inside the sandbox."""
        from sandbox.inference import get_default_commands
        cmds = get_default_commands(self.language, self.package_manager)
        test_cmd = cmds.get("test")
        
        if not test_cmd:
            logger.warning("No test command found for this environment.")
            return {"success": False, "exit_code": -1, "stdout": "", "stderr": "No test command found."}
            
        logger.info(f"Running test suite using command: {test_cmd}")
        res = self.sandbox_manager.execute_command(test_cmd)
        return {
            "success": res["exit_code"] == 0,
            "exit_code": res["exit_code"],
            "stdout": res["stdout"],
            "stderr": res["stderr"]
        }
