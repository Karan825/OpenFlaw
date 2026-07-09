import os
import ast
import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class PythonOutlineVisitor(ast.NodeVisitor):
    """AST visitor to extract class and function definitions from Python code."""
    def __init__(self):
        self.outline = []
        self.indent = "  "

    def visit_ClassDef(self, node):
        self.outline.append(f"{self.indent}class {node.name}:")
        old_indent = self.indent
        self.indent += "    "
        self.generic_visit(node)
        self.indent = old_indent

    def visit_FunctionDef(self, node):
        # Gather argument names
        args = [arg.arg for arg in node.args.args]
        self.outline.append(f"{self.indent}def {node.name}({', '.join(args)}):")
        # We don't recurse into function bodies to avoid scanning nested definitions
        
    def visit_AsyncFunctionDef(self, node):
        args = [arg.arg for arg in node.args.args]
        self.outline.append(f"{self.indent}async def {node.name}({', '.join(args)}):")


class RepoMapTool:
    """
    Generates a structural layout map of the codebase to help the agent
    locate relevant classes and functions.
    """
    def __init__(self, repo_dir: str):
        self.repo_dir = repo_dir
        self.exclude_dirs = {
            ".git", "node_modules", "__pycache__", "venv", ".venv",
            "build", "dist", "target", ".idea", ".vscode", "egg-info"
        }
        self.exclude_files = {
            "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
            "poetry.lock", "uv.lock", "seed_issues.json"
        }

        # Regex patterns for fast extraction of structural symbols in other languages
        self.go_pattern = re.compile(r'^\s*(func|type)\s+([a-zA-Z0-9_]+.*)$')
        self.rs_pattern = re.compile(r'^\s*(pub\s+)?(fn|struct|impl|trait)\s+([a-zA-Z0-9_]+.*)$')
        self.js_pattern = re.compile(r'^\s*(export\s+)?(class|function|interface|type)\s+([a-zA-Z0-9_]+.*)$')

    def _should_exclude(self, path: str) -> bool:
        parts = os.path.relpath(path, self.repo_dir).split(os.sep)
        for part in parts:
            if part in self.exclude_dirs:
                return True
        if os.path.basename(path) in self.exclude_files:
            return True
        return False

    def _parse_python(self, content: str) -> List[str]:
        try:
            tree = ast.parse(content)
            visitor = PythonOutlineVisitor()
            visitor.visit(tree)
            return visitor.outline
        except SyntaxError:
            return ["  [Syntax Error while parsing AST]"]
        except Exception as e:
            return [f"  [Failed to parse AST: {str(e)}]"]

    def _parse_regex(self, content: str, pattern: re.Pattern) -> List[str]:
        signatures = []
        for line in content.splitlines():
            match = pattern.match(line)
            if match:
                signatures.append(f"  {match.group(0).strip()}")
        return signatures[:30]  # Limit to first 30 matches to keep mapping concise

    def generate_map(self) -> str:
        """
        Scans the codebase recursively and generates a structured directory
        and symbol outline.
        """
        output = ["Repository Structure Map:"]
        
        for root, dirs, files in os.walk(self.repo_dir):
            # Prune exclude directories in-place
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            
            for file in sorted(files):
                full_path = os.path.join(root, file)
                if self._should_exclude(full_path):
                    continue
                
                rel_path = os.path.relpath(full_path, self.repo_dir).replace("\\", "/")
                _, ext = os.path.splitext(file)
                
                if ext not in [".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs"]:
                    # Just add standard text/config files as paths without structure
                    output.append(f"\n{rel_path}")
                    continue
                
                output.append(f"\n{rel_path}:")
                
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    
                    signatures = []
                    if ext == ".py":
                        signatures = self._parse_python(content)
                    elif ext == ".go":
                        signatures = self._parse_regex(content, self.go_pattern)
                    elif ext == ".rs":
                        signatures = self._parse_regex(content, self.rs_pattern)
                    elif ext in [".js", ".jsx", ".ts", ".tsx"]:
                        signatures = self._parse_regex(content, self.js_pattern)
                        
                    if signatures:
                        output.extend(signatures)
                    else:
                        output.append("  [No high-level classes or functions found]")
                except Exception as e:
                    output.append(f"  [Failed to read: {str(e)}]")
                    
        return "\n".join(output)
