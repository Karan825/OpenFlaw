import os
import json
import logging
import tempfile
import shutil
import subprocess
from dotenv import load_dotenv

# Load env variables from .env file
load_dotenv()
from github_client import GitHubAppClient
from sandbox.manager import SandboxManager
from sandbox.inference import detect_environment_from_dir
from agent.runner import AgentRunner
from agent.tools.terminal import TerminalTool
from agent.tools.file_editor import FileEditorTool
from agent.tools.ripgrep import RipgrepTool
from agent.tools.repo_map import RepoMapTool
from verification.ci_runner import CIRunner
from verification.coverage import CoverageTracker
from safety.diff_guard import DiffGuard
from safety.scrubber import SecretScrubber

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def run_worker(payload: dict) -> dict:
    """Coordinates the end-to-end sandbox execution and PR submission."""
    scrubber = SecretScrubber()
    
    # 1. Parse payload details
    repo_url = payload.get("repo_url")
    repo_full_name = payload.get("repo_full_name")
    issue_number = payload.get("issue_number")
    issue_title = payload.get("title", "")
    issue_body = payload.get("body", "")
    installation_id = payload.get("installation_id")
    
    if not (repo_url and repo_full_name and issue_number):
        raise ValueError("Missing critical fields in SQS payload.")
        
    logger.info(f"Processing task: Repo={repo_full_name}, Issue/PR={issue_number}")
    
    # 2. Get GitHub Installation access token
    gh_client = GitHubAppClient(installation_id=str(installation_id))
    token = gh_client.get_installation_token()
    
    # 3. Create a local temporary clone for RepoMap analysis
    temp_dir = tempfile.mkdtemp()
    local_repo_dir = os.path.join(temp_dir, "repo")
    
    try:
        # Clone locally in the worker container
        logger.info(f"Cloning repo locally to {local_repo_dir}")
        authenticated_url = repo_url.replace("https://", f"https://x-access-token:{token}@")
        subprocess.run(["git", "clone", authenticated_url, local_repo_dir], check=True, capture_output=True)
        
        # 4. Spin up the E2B sandbox and clone the repo inside
        sandbox_mgr = SandboxManager()
        sandbox_mgr.start()
        sandbox_mgr.clone_repo(repo_url, token=token)
        
        # Set up Git config inside the sandbox
        sandbox_mgr.setup_git_config()
        
        # Create an agent fix branch
        branch_name = f"agent-fix-issue-{issue_number}"
        sandbox_mgr.create_branch(branch_name)
        
        # 5. Detect project environment (language, packages)
        env = detect_environment_from_dir(local_repo_dir)
        language = env.get("language", "unknown")
        package_manager = env.get("package_manager")
        logger.info(f"Detected Environment: Language={language}, Package Manager={package_manager}")
        
        # Initialize CI & Coverage Trackers
        ci_runner = CIRunner(sandbox_mgr, language, package_manager)
        cov_tracker = CoverageTracker(sandbox_mgr, language, package_manager)
        
        # Run baseline coverage before agent makes edits
        logger.info("Running baseline tests and coverage...")
        ci_runner.install_dependencies()
        baseline_cov = cov_tracker.run_coverage()
        logger.info(f"Baseline coverage: {baseline_cov}%")
        
        # 6. Initialize Agent Tools
        terminal_tool = TerminalTool(sandbox_mgr)
        file_editor_tool = FileEditorTool(sandbox_mgr)
        ripgrep_tool = RipgrepTool(sandbox_mgr)
        repo_map_tool = RepoMapTool(local_repo_dir)
        
        tools = {
            "repo_map": repo_map_tool,
            "ripgrep": ripgrep_tool,
            "read_file": file_editor_tool,
            "write_file": file_editor_tool,
            "edit_file": file_editor_tool,
            "execute_command": terminal_tool
        }
        
        # 7. Run Agent ReAct Loop
        runner = AgentRunner(tools, max_turns=30, max_budget_usd=20.0)
        result = runner.run(issue_title, issue_body)
        logger.info(f"Agent finished. Status={result['status']}, Cost=${result['total_cost_usd']}")
        
        # 8. Post-Fix Verification and Safety Checks
        if result["status"] == "success":
            # Safety checks - path restrictions
            guard = DiffGuard(sandbox_mgr, sandbox_mgr.repo_dir)
            is_safe, offending = guard.validate_diff()
            
            if not is_safe:
                error_msg = f"Safety Block: Agent attempted to modify protected paths: {offending}"
                logger.error(error_msg)
                gh_client.post_pr_comment(repo_full_name, issue_number, f"**Safety Check Failed**: An autonomous run was aborted because the agent attempted to modify protected file paths: `{offending}`.")
                result["status"] = "safety_violation"
                return result
                
            # Verify that tests pass post-fix
            logger.info("Running post-fix test suite verification...")
            test_res = ci_runner.run_tests()
            
            if not test_res["success"]:
                error_msg = f"Verification Failed: Test suite failed after edits.\nStdout:\n{test_res['stdout']}\nStderr:\n{test_res['stderr']}"
                logger.warning(error_msg)
                scrubbed_err = scrubber.scrub(test_res["stderr"] or test_res["stdout"])
                gh_client.post_pr_comment(
                    repo_full_name, 
                    issue_number, 
                    f"❌ **Verification Failed**: The agent proposed a fix but the test suite failed inside the sandbox:\n```\n{scrubbed_err[:1000]}\n```"
                )
                result["status"] = "test_failure"
                return result
                
            # Compute coverage delta
            after_cov = cov_tracker.run_coverage()
            cov_delta = cov_tracker.compute_delta(baseline_cov, after_cov)
            logger.info(f"Coverage delta: {cov_delta}% (Baseline={baseline_cov}%, After={after_cov}%)")
            
            # 9. Push branch and open Pull Request
            logger.info("Pushing agent branch to GitHub...")
            push_res = sandbox_mgr.execute_command(f"git push origin {branch_name}")
            if push_res["exit_code"] != 0:
                raise RuntimeError(f"Failed to push branch: {push_res['stderr']}")
                
            # Construct PR body
            pr_body = (
                f"##Agent Fix Summary\n\n"
                f"This Pull Request has been generated autonomously by the coding agent to resolve Issue #{issue_number}.\n\n"
                f"### Rationale / Explanation\n"
                f"{result['final_answer']}\n\n"
                f"### Stats\n"
                f"- **Model**: `{runner.model}`\n"
                f"- **Turns Taken**: `{result['turns']}`\n"
                f"- **API Cost**: `${result['total_cost_usd']}`\n"
                f"- **Time Elapsed**: `{result['execution_time_seconds']} seconds`\n"
                f"- **Test Suite**: Passed\n"
            )
            
            if baseline_cov is not None and after_cov is not None:
                pr_body += f"- **Coverage Delta**: `{cov_delta:+.2f}%` (from `{baseline_cov}%` to `{after_cov}%`)\n"
                
            pr_title = f"Fix: {issue_title}"
            pr_number = gh_client.create_pull_request(
                repo_name=repo_full_name,
                title=pr_title,
                body=pr_body,
                head=branch_name,
                base="main"
            )
            
            # Label PR
            labels = ["agent-fix"]
            if cov_delta < -2.0:
                labels.append("needs-review")
                gh_client.post_pr_comment(
                    repo_full_name, 
                    pr_number, 
                    "**Warning**: Test coverage dropped by more than 2% during this fix. Please review carefully."
                )
            gh_client.add_labels_to_pr(repo_full_name, pr_number, labels)
            
        else:
            # Agent failed to find a solution
            logger.warning(f"Agent stopped without successful resolution. Status: {result['status']}")
            gh_client.post_pr_comment(
                repo_full_name, 
                issue_number, 
                f"**Agent Run Stopped**: The autonomous worker stopped without proposing a fix. Reason: `{result['status']}`."
            )
            
    except Exception as e:
        logger.exception(f"Unexpected error running worker pipeline: {e}")
        raise
    finally:
        # Cleanup E2B sandbox and local files
        if 'sandbox_mgr' in locals():
            sandbox_mgr.close()
        shutil.rmtree(temp_dir, ignore_errors=True)
        
    return result

if __name__ == "__main__":
    # Expect payload string to be passed via PAYLOAD env variable
    payload_str = os.environ.get("PAYLOAD")
    if payload_str:
        try:
            payload_data = json.loads(payload_str)
            run_worker(payload_data)
        except Exception as err:
            print(f"Error executing worker main: {err}")
    else:
        logger.error("No PAYLOAD environment variable provided.")
