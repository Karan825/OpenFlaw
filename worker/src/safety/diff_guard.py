import os
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

class DiffGuard:
    """
    Enforces path-scoped write restrictions and branch protection checks
    to ensure the agent doesn't modify sensitive configuration files
    (e.g., GitHub Actions workflows, infrastructure scripts).
    """
    def __init__(self, sandbox_manager, repo_dir: str):
        self.sandbox_manager = sandbox_manager
        self.repo_dir = repo_dir
        
        # Blacklist of directories or filename patterns the agent is forbidden to modify
        self.forbidden_patterns = [
            ".github/",            # Block GitHub workflows and settings
            "infra/",              # Block Terraform / Cloud infra changes
            ".env",                # Block environment secret file modifications
            "Dockerfile",          # Block docker image configuration changes
            "docker-compose.yml"   # Block docker compose configurations
        ]

    def get_modified_files(self) -> List[str]:
        """
        Runs git diff/status in the sandbox to find all modified, added,
        or deleted files.
        """
        # Run git status --porcelain in sandbox to find all uncommitted/committed changes
        res = self.sandbox_manager.execute_command("git status --porcelain")
        if res["exit_code"] != 0:
            logger.warning(f"Failed to check git status: {res['stderr']}")
            return []
            
        modified_files = []
        for line in res["stdout"].splitlines():
            # Line format is usually: XY path/to/file
            if len(line) > 3:
                filepath = line[3:].strip()
                # Handle renamed files (e.g. R  old -> new)
                if " -> " in filepath:
                    filepath = filepath.split(" -> ")[-1].strip()
                modified_files.append(filepath)
                
        # Also run git diff against origin/main to get all changes on this branch
        res_diff = self.sandbox_manager.execute_command("git diff --name-only origin/main...HEAD")
        if res_diff["exit_code"] == 0:
            for filepath in res_diff["stdout"].splitlines():
                f = filepath.strip()
                if f and f not in modified_files:
                    modified_files.append(f)
                    
        return modified_files

    def validate_diff(self) -> Tuple[bool, List[str]]:
        """
        Checks all modified files against the forbidden patterns.
        
        Returns:
            (is_safe, list_of_offending_files)
        """
        modified_files = self.get_modified_files()
        offending_files = []
        
        for filepath in modified_files:
            normalized_path = filepath.replace("\\", "/").strip()
            
            for pattern in self.forbidden_patterns:
                if pattern.endswith("/"):
                    # Match directory structure
                    if normalized_path.startswith(pattern) or f"/{pattern}" in normalized_path:
                        offending_files.append(filepath)
                        break
                else:
                    # Match specific file name or suffix
                    if normalized_path == pattern or normalized_path.endswith("/" + pattern):
                        offending_files.append(filepath)
                        break
                        
        is_safe = len(offending_files) == 0
        if not is_safe:
            logger.warning(f"DiffGuard flagged forbidden file edits: {offending_files}")
            
        return is_safe, offending_files
