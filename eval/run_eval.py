import os
import json
import time
import sys
import logging
import tempfile
from dotenv import load_dotenv

# Load env variables from .env file
load_dotenv()

# Add worker/src to path so we can import worker modules
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "worker", "src"))

from sandbox.manager import SandboxManager
from agent.runner import AgentRunner
from agent.tools.terminal import TerminalTool
from agent.tools.file_editor import FileEditorTool
from agent.tools.ripgrep import RipgrepTool
from agent.tools.repo_map import RepoMapTool

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def run_evaluation():
    # Load seed issues
    eval_dir = os.path.dirname(__file__)
    seed_path = os.path.join(eval_dir, "seed_issues.json")
    results_path = os.path.join(eval_dir, "eval_results.json")
    
    if not os.path.exists(seed_path):
        logger.error(f"Seed issues file not found at {seed_path}")
        return
        
    with open(seed_path, "r") as f:
        issues = json.load(f)
        
    logger.info(f"Loaded {len(issues)} seed issues for evaluation.")
    
    results = []
    
    # E2B Sandbox evaluation requires credentials
    if not os.environ.get("E2B_API_KEY"):
        logger.error("E2B_API_KEY is not set. Sandbox evaluation requires E2B credentials.")
        print("\nPlease export E2B_API_KEY before running evaluation.")
        return

    for idx, issue in enumerate(issues):
        issue_id = issue.get("id", f"issue-{idx}")
        logger.info(f"Evaluating {issue_id}...")
        
        sandbox_mgr = SandboxManager()
        try:
            # Start clean sandbox
            sandbox_mgr.start()
            
            repo_url = issue.get("repo_url")
            
            # Setup code structures inside the E2B sandbox for evaluation issues
            if "mock" in repo_url:
                logger.info(f"Setting up mock codebase structure for {issue_id} inside sandbox...")
                sandbox_mgr.execute_command("mkdir -p src/utils")
                if issue_id == "test-issue-01":
                    sandbox_mgr.sandbox.files.write(
                        "/home/user/repo/src/utils/math.py",
                        "def divide(a, b):\n    # TODO: Gracefully handle division by zero (return 0)\n    return a / b\n"
                    )
                    # Add tests
                    sandbox_mgr.execute_command("mkdir -p tests")
                    sandbox_mgr.sandbox.files.write(
                        "/home/user/repo/tests/test_math.py",
                        "from src.utils.math import divide\ndef test_divide():\n    assert divide(6, 2) == 3\n"
                    )
                elif issue_id == "test-issue-02":
                    sandbox_mgr.sandbox.files.write(
                        "/home/user/repo/src/utils/scrubber.py",
                        "def clean_log(log_text):\n    # TODO: strip API keys like sk- or ghp_\n    return log_text\n"
                    )
            else:
                # Clone the real repo
                sandbox_mgr.clone_repo(repo_url)

            # Setup tools (RepoMap needs a local path to scan files recursively)
            with tempfile.TemporaryDirectory() as local_temp:
                # Mock RepoMapTool local path with matching files
                if issue_id == "test-issue-01":
                    os.makedirs(os.path.join(local_temp, "src", "utils"), exist_ok=True)
                    with open(os.path.join(local_temp, "src", "utils", "math.py"), "w") as mf:
                        mf.write("def divide(a, b):\n    return a / b\n")
                elif issue_id == "test-issue-02":
                    os.makedirs(os.path.join(local_temp, "src", "utils"), exist_ok=True)
                    with open(os.path.join(local_temp, "src", "utils", "scrubber.py"), "w") as sf:
                        sf.write("def clean_log(log_text):\n    return log_text\n")

                repo_map_tool = RepoMapTool(local_temp)
                terminal_tool = TerminalTool(sandbox_mgr)
                file_editor_tool = FileEditorTool(sandbox_mgr)
                ripgrep_tool = RipgrepTool(sandbox_mgr)
                
                tools = {
                    "repo_map": repo_map_tool,
                    "ripgrep": ripgrep_tool,
                    "read_file": file_editor_tool,
                    "write_file": file_editor_tool,
                    "edit_file": file_editor_tool,
                    "execute_command": terminal_tool
                }
                
                # Execute agent loop
                runner = AgentRunner(tools, max_turns=30, max_budget_usd=20.0)
                run_res = runner.run(issue.get("title"), issue.get("body"))
                
                eval_item = {
                    "id": issue_id,
                    "title": issue.get("title"),
                    "status": run_res["status"],
                    "turns": run_res["turns"],
                    "cost_usd": run_res["total_cost_usd"],
                    "time_seconds": run_res["execution_time_seconds"],
                    "final_answer": run_res["final_answer"]
                }
                results.append(eval_item)
                logger.info(f"Finished {issue_id}: Status={run_res['status']}, Cost=${run_res['total_cost_usd']}")

        except Exception as err:
            logger.error(f"Error evaluating {issue_id}: {err}")
            results.append({
                "id": issue_id,
                "title": issue.get("title"),
                "status": "eval_error",
                "turns": 0,
                "cost_usd": 0.0,
                "time_seconds": 0.0,
                "final_answer": None
            })
        finally:
            sandbox_mgr.close()

    # Compile results summary
    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_evaluated": len(results),
        "successful_resolutions": sum(1 for r in results if r["status"] == "success"),
        "average_turns": sum(r["turns"] for r in results) / len(results) if results else 0,
        "average_cost_usd": sum(r["cost_usd"] for r in results) / len(results) if results else 0,
        "average_time_seconds": sum(r["time_seconds"] for r in results) / len(results) if results else 0,
        "issues": results
    }
    
    with open(results_path, "w") as f:
        json.dump(summary, f, indent=2)
        
    print("\n" + "="*50)
    print(" EVALUATION COMPLETED SUMMARY")
    print("="*50)
    print(f"Total Evaluated        : {summary['total_evaluated']}")
    print(f"Successful PRs Created : {summary['successful_resolutions']}")
    print(f"Pass Rate              : {summary['successful_resolutions'] / summary['total_evaluated'] * 100:.1f}%")
    print(f"Avg Turns per Run      : {summary['average_turns']:.1f}")
    print(f"Avg Cost per PR        : ${summary['average_cost_usd']:.4f}")
    print(f"Avg Time per PR        : {summary['average_time_seconds']:.1f} seconds")
    print("="*50)

if __name__ == "__main__":
    run_evaluation()
