import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class FileEditorTool:
    """
    Tool that allows the agent to read, write, and patch files in the sandbox.
    """
    def __init__(self, sandbox_manager):
        self.sandbox_manager = sandbox_manager

    def _get_absolute_path(self, filepath: str) -> str:
        # Resolve path relative to the active repository directory in the sandbox
        if filepath.startswith("/"):
            return filepath
        return os.path.join(self.sandbox_manager.repo_dir, filepath).replace("\\", "/")

    def read_file(self, filepath: str, start_line: int = 1, end_line: Optional[int] = None) -> Dict[str, Any]:
        """Reads content from a file in the sandbox."""
        if not self.sandbox_manager.sandbox:
            return {"success": False, "error": "Sandbox is not active."}
            
        abs_path = self._get_absolute_path(filepath)
        try:
            # Read from E2B sandbox filesystem
            content = self.sandbox_manager.sandbox.files.read(abs_path)
            lines = content.splitlines()
            
            total_lines = len(lines)
            start_idx = max(0, start_line - 1)
            end_idx = min(total_lines, end_line if end_line is not None else total_lines)
            
            selected_content = "\n".join(lines[start_idx:end_idx])
            return {
                "success": True,
                "content": selected_content,
                "start_line": start_idx + 1,
                "end_line": end_idx,
                "total_lines": total_lines
            }
        except Exception as e:
            logger.error(f"Error reading file {abs_path}: {e}")
            return {"success": False, "error": f"Failed to read file: {str(e)}"}

    def write_file(self, filepath: str, content: str) -> Dict[str, Any]:
        """Writes/overwrites content to a file in the sandbox."""
        if not self.sandbox_manager.sandbox:
            return {"success": False, "error": "Sandbox is not active."}
            
        abs_path = self._get_absolute_path(filepath)
        try:
            # Create parent directories inside the sandbox if they don't exist
            parent_dir = os.path.dirname(abs_path)
            if parent_dir and parent_dir != "/":
                self.sandbox_manager.sandbox.commands.run(f"mkdir -p {parent_dir}")
                
            self.sandbox_manager.sandbox.files.write(abs_path, content)
            return {"success": True, "message": f"Successfully wrote to {filepath}"}
        except Exception as e:
            logger.error(f"Error writing file {abs_path}: {e}")
            return {"success": False, "error": f"Failed to write file: {str(e)}"}

    def edit_file(self, filepath: str, target_content: str, replacement_content: str) -> Dict[str, Any]:
        """
        Searches for target_content in the file and replaces it with replacement_content.
        Only succeeds if target_content is found exactly once in the file to prevent errors.
        """
        if not self.sandbox_manager.sandbox:
            return {"success": False, "error": "Sandbox is not active."}
            
        abs_path = self._get_absolute_path(filepath)
        try:
            # Read current content
            content = self.sandbox_manager.sandbox.files.read(abs_path)
            
            # Count occurrences of target_content
            count = content.count(target_content)
            
            if count == 0:
                return {
                    "success": False,
                    "error": "The target_content to replace was not found in the file. Make sure spelling, capitalization, and indentation match exactly."
                }
            elif count > 1:
                return {
                    "success": False,
                    "error": f"The target_content was found {count} times in the file. Please provide more surrounding context to make it unique."
                }
                
            # Perform replacement
            new_content = content.replace(target_content, replacement_content, 1)
            self.sandbox_manager.sandbox.files.write(abs_path, new_content)
            
            return {"success": True, "message": f"Successfully edited {filepath}"}
        except Exception as e:
            logger.error(f"Error editing file {abs_path}: {e}")
            return {"success": False, "error": f"Failed to edit file: {str(e)}"}
