import os
import logging
from e2b import Sandbox

logger = logging.getLogger(__name__)

class SandboxManager:
    """
    Manages the E2B Sandbox lifecycle, repository checkout, git branching,
    and remote command execution.
    """
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("E2B_API_KEY")
        self.sandbox = None
        self.repo_dir = "/home/user/repo"  # Target path inside E2B container

    def start(self, template: str = "base") -> Sandbox:
        """Starts a new E2B Sandbox."""
        logger.info(f"Starting E2B sandbox with template: {template}")
        if self.api_key:
            os.environ["E2B_API_KEY"] = self.api_key
        self.sandbox = Sandbox.create(template=template)
        return self.sandbox

    def clone_repo(self, clone_url: str, token: str = None) -> str:
        """
        Clones the repository into the sandbox.
        If a token is provided, embeds it into the clone URL for authentication.
        """
        if not self.sandbox:
            raise RuntimeError("Sandbox is not started.")
            
        logger.info(f"Cloning repo: {clone_url}")
        
        # Inject token into URL if present (e.g. GitHub App installation token)
        if token:
            if clone_url.startswith("https://"):
                url_without_schema = clone_url.split("https://")[-1]
                authenticated_url = f"https://x-access-token:{token}@{url_without_schema}"
            else:
                authenticated_url = clone_url
        else:
            authenticated_url = clone_url

        # E2B commands are run in /home/user by default
        clone_cmd = f"git clone {authenticated_url} {self.repo_dir}"
        logger.info(f"Executing: git clone <redacted_token> {self.repo_dir}")
        
        res = self.sandbox.commands.run(clone_cmd)
        if res.exit_code != 0:
            raise RuntimeError(f"Failed to clone repository: {res.stderr}")
            
        return self.repo_dir

    def setup_git_config(self, username: str = "agent-bot", email: str = "agent-bot@users.noreply.github.com"):
        """Sets up git configurations in the sandbox."""
        if not self.sandbox:
            raise RuntimeError("Sandbox is not started.")
            
        logger.info("Setting up git config inside the sandbox")
        self.sandbox.commands.run(f"git -C {self.repo_dir} config user.name '{username}'")
        self.sandbox.commands.run(f"git -C {self.repo_dir} config user.email '{email}'")

    def create_branch(self, branch_name: str):
        """Creates and switches to a new git branch in the sandbox."""
        if not self.sandbox:
            raise RuntimeError("Sandbox is not started.")
            
        logger.info(f"Creating new branch: {branch_name}")
        res = self.sandbox.commands.run(f"git -C {self.repo_dir} checkout -b {branch_name}")
        if res.exit_code != 0:
            raise RuntimeError(f"Failed to create git branch {branch_name}: {res.stderr}")

    def execute_command(self, cmd: str, workdir: str = None) -> dict:
        """Executes a command inside the sandbox."""
        if not self.sandbox:
            raise RuntimeError("Sandbox is not started.")
            
        target_dir = workdir or self.repo_dir
        logger.info(f"Executing command in {target_dir}: {cmd}")
        try:
            res = self.sandbox.commands.run(cmd, cwd=target_dir)
            return {
                "stdout": res.stdout,
                "stderr": res.stderr,
                "exit_code": res.exit_code
            }
        except Exception as e:
            # Catch CommandExitException which is raised when commands exit with non-zero codes
            if hasattr(e, "result") and e.result is not None:
                return {
                    "stdout": getattr(e.result, "stdout", ""),
                    "stderr": getattr(e.result, "stderr", ""),
                    "exit_code": getattr(e.result, "exit_code", 1)
                }
            elif hasattr(e, "exit_code"):
                return {
                    "stdout": getattr(e, "stdout", ""),
                    "stderr": getattr(e, "stderr", ""),
                    "exit_code": e.exit_code
                }
            else:
                return {
                    "stdout": "",
                    "stderr": str(e),
                    "exit_code": 127
                }

    def close(self):
        """Closes the sandbox."""
        if self.sandbox:
            logger.info("Closing E2B sandbox")
            self.sandbox.kill()
            self.sandbox = None
