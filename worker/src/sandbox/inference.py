import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

def detect_environment_from_files(files: List[str]) -> Dict[str, Optional[str]]:
    """
    Detects the programming language and package manager.
    Supports nested paths by finding the most relevant build/lock file.
    """
    # Normalize all file paths to lowercase for matching
    normalized_files = [f.lower().replace("\\", "/") for f in files]

    # Helper to check if a specific filename exists anywhere in the file list
    def find_file(target_name: str) -> Optional[str]:
        for f in normalized_files:
            # Matches target_name at the root or at the end of a path (e.g., "server/requirements.txt")
            if f == target_name or f.endswith("/" + target_name):
                return f
        return None

    # 1. Rust Detection
    if find_file("cargo.toml"):
        return {"language": "rust", "package_manager": "cargo", "build_tool": "cargo"}

    # 2. Go Detection
    if find_file("go.mod"):
        return {"language": "go", "package_manager": "go mod", "build_tool": "go"}

    # 3. Python Detection (ordered by modern toolchain priority)
    if find_file("uv.lock"):
        return {"language": "python", "package_manager": "uv", "build_tool": "uv"}
    if find_file("poetry.lock"):
        return {"language": "python", "package_manager": "poetry", "build_tool": "poetry"}
    if find_file("pipfile") or find_file("pipfile.lock"):
        return {"language": "python", "package_manager": "pipenv", "build_tool": "pipenv"}
    if find_file("requirements.txt"):
        return {"language": "python", "package_manager": "pip", "build_tool": "pip"}
    if find_file("pyproject.toml"):
        return {"language": "python", "package_manager": "pip", "build_tool": "pip"}

    # 4. Node.js (JavaScript / TypeScript) Detection
    if find_file("pnpm-lock.yaml"):
        return {"language": "javascript", "package_manager": "pnpm", "build_tool": "pnpm"}
    if find_file("package-lock.json"):
        return {"language": "javascript", "package_manager": "npm", "build_tool": "npm"}
    if find_file("yarn.lock"):
        return {"language": "javascript", "package_manager": "yarn", "build_tool": "yarn"}
    if find_file("package.json"):
        return {"language": "javascript", "package_manager": "npm", "build_tool": "npm"}

    # Default fallback - Agent will deduce it dynamically
    return {"language": "unknown", "package_manager": None, "build_tool": None}


def detect_environment_from_dir(dir_path: str, max_depth: int = 2) -> Dict[str, Optional[str]]:
    """
    Scans a directory recursively up to `max_depth` to collect files
    and detect the environment.
    """
    all_files = []
    start_depth = dir_path.rstrip(os.sep).count(os.sep)
    
    try:
        for root, dirs, files in os.walk(dir_path):
            current_depth = root.count(os.sep) - start_depth
            if current_depth >= max_depth:
                # Clear dirs to prevent walking deeper
                dirs.clear()
                
            for file in files:
                # Store relative paths
                rel_path = os.path.relpath(os.path.join(root, file), dir_path)
                all_files.append(rel_path)
                
        return detect_environment_from_files(all_files)
    except Exception as e:
        logger.error(f"Error scanning directory {dir_path}: {e}")
        return {"language": "unknown", "package_manager": None, "build_tool": None}


def get_default_commands(language: str, package_manager: str, sub_dir: str = "") -> Dict[str, str]:
    """
    Returns standard commands to install dependencies and run tests.
    If sub_dir is specified (for monorepos), commands will run in that directory.
    """
    prefix = f"cd {sub_dir} && " if sub_dir else ""
    
    if language == "python":
        if package_manager == "uv":
            return {"install": f"{prefix}uv sync", "test": f"{prefix}uv run pytest"}
        elif package_manager == "poetry":
            return {"install": f"{prefix}poetry install", "test": f"{prefix}poetry run pytest"}
        elif package_manager == "pipenv":
            return {"install": f"{prefix}pipenv install --dev", "test": f"{prefix}pipenv run pytest"}
        else:
            return {"install": f"{prefix}pip install -r requirements.txt", "test": f"{prefix}pytest"}
            
    elif language == "javascript":
        if package_manager == "pnpm":
            return {"install": f"{prefix}pnpm install", "test": f"{prefix}pnpm test"}
        elif package_manager == "yarn":
            return {"install": f"{prefix}yarn install", "test": f"{prefix}yarn test"}
        else:
            return {"install": f"{prefix}npm install", "test": f"{prefix}npm test"}
            
    elif language == "go":
        return {"install": f"{prefix}go get ./...", "test": f"{prefix}go test ./..."}
        
    elif language == "rust":
        return {"install": f"{prefix}cargo build", "test": f"{prefix}cargo test"}
        
    return {"install": "", "test": ""}
