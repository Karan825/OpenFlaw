# Parses and calculates coverage delta
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class CoverageTracker:
    """
    Measures codebase test coverage before and after agent modifications
    to compute coverage delta and flag regressions.
    """
    def __init__(self, sandbox_manager, language: str, package_manager: str):
        self.sandbox_manager = sandbox_manager
        self.language = language
        self.package_manager = package_manager

    def run_coverage(self) -> Optional[float]:
        """
        Runs coverage tools inside the sandbox and parses the overall coverage percentage.
        Supports Python/pytest coverage parsing.
        """
        if self.language != "python":
            logger.info(f"Coverage collection not fully implemented for language: {self.language}. Skipping.")
            return None
            
        try:
            # We run pytest under coverage and export results to JSON
            run_cmd = "PYTHONPATH=. coverage run -m pytest && coverage json -o coverage_report.json"
            res = self.sandbox_manager.execute_command(run_cmd)
            
            if res["exit_code"] != 0:
                logger.info("coverage command failed, trying fallback: pytest --cov")
                fallback_cmd = "PYTHONPATH=. pytest --cov=. --cov-report=json:coverage_report.json"
                res = self.sandbox_manager.execute_command(fallback_cmd)
                if res["exit_code"] != 0:
                    logger.warning("Could not execute test coverage suite.")
                    return None

            # Read the generated JSON file from the sandbox filesystem
            report_path = f"{self.sandbox_manager.repo_dir}/coverage_report.json"
            content = self.sandbox_manager.sandbox.files.read(report_path)
            report_data = json.loads(content)
            
            # Extract total coverage percentage
            percent = report_data.get("totals", {}).get("percent_covered")
            if percent is not None:
                return float(percent)
                
        except Exception as e:
            logger.error(f"Error parsing Python coverage report: {e}")
            
        return None

    def compute_delta(self, before_pct: Optional[float], after_pct: Optional[float]) -> float:
        """
        Computes coverage delta (after - before).
        A negative delta indicates a drop in coverage.
        """
        if before_pct is None or after_pct is None:
            return 0.0
        return after_pct - before_pct
