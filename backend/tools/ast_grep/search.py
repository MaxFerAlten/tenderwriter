"""AST-grep tools for pattern-aware code search and replacement."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ASTMatch:
    """Represents a match from AST-grep search."""
    file_path: str
    line: int
    column: int
    matched_content: str
    context: str | None = None


@dataclass
class ASTReplacement:
    """Represents a replacement operation."""
    file_path: str
    matches: list[ASTMatch]
    new_content: str


class ASTGrep:
    """
    AST-grep wrapper for pattern-aware code search and replacement.
    
    Supports 25+ languages with semantic pattern matching.
    """

    def __init__(self, binary_path: str = "ast-grep"):
        self.binary = binary_path
        self.logger = logging.getLogger(f"{__name__}.ASTGrep")

    def search(
        self,
        pattern: str,
        lang: str | None = None,
        file_pattern: str = "*",
        dir: str = "."
    ) -> list[ASTMatch]:
        """
        Search for AST pattern matches.
        
        Args:
            pattern: AST-grep pattern (e.g., "console.log($ARG)")
            lang: Language (auto-detected if None)
            file_pattern: File pattern (default: *)
            dir: Directory to search
            
        Returns:
            List of matches with locations
        """
        matches = []
        try:
            cmd = [
                self.binary,
                "run",
                "--json",
                "--rule", pattern
            ]
            
            if lang:
                cmd.extend(["--lang", lang])
            
            cmd.extend(["--glob", file_pattern, dir])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0 and result.stdout:
                for line in result.stdout.split("\n"):
                    if line.strip():
                        try:
                            data = json.loads(line)
                            matches.append(ASTMatch(
                                file_path=data.get("file_path", ""),
                                line=data.get("line", 0),
                                column=data.get("column", 0),
                                matched_content=data.get("content", ""),
                                context=data.get("context")
                            ))
                        except json.JSONDecodeError:
                            continue

        except subprocess.TimeoutExpired:
            self.logger.error("AST-grep search timed out")
        except FileNotFoundError:
            self.logger.error(f"ast-grep not found at {self.binary}")
        except Exception as e:
            self.logger.error(f"AST-grep search failed: {e}")

        return matches

    def replace(
        self,
        pattern: str,
        replacement: str,
        lang: str | None = None,
        file_pattern: str = "*",
        dir: str = ".",
        dry_run: bool = True
    ) -> dict[str, Any]:
        """
        Replace AST pattern matches with new code.
        
        Args:
            pattern: AST-grep pattern to find
            replacement: AST-grep replacement pattern
            lang: Language (auto-detected if None)
            file_pattern: File pattern
            dir: Directory to search
            dry_run: If True, don't make changes
            
        Returns:
            Dictionary with results
        """
        results = {
            "matches": 0,
            "files_modified": [],
            "errors": []
        }

        try:
            cmd = [
                self.binary,
                "rewrite",
                "--rule", pattern,
                "--rewrite", replacement
            ]
            
            if lang:
                cmd.extend(["--lang", lang])
            
            cmd.extend(["--glob", file_pattern])
            
            if dry_run:
                cmd.append("--dry-run")
            
            cmd.append(dir)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.stdout:
                output = result.stdout
                results["matches"] = output.count("REWRITE")
                results["dry_run"] = dry_run
                results["output"] = output

        except subprocess.TimeoutExpired:
            results["errors"].append("AST-grep replace timed out")
        except FileNotFoundError:
            results["errors"].append(f"ast-grep not found at {self.binary}")
        except Exception as e:
            results["errors"].append(str(e))

        return results

    def list_rules(self, dir: str = ".") -> list[str]:
        """
        List available rules in a directory.
        
        Args:
            dir: Directory to search for rules
            
        Returns:
            List of rule files
        """
        rules = []
        try:
            result = subprocess.run(
                [self.binary, "list", "--rules", dir],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                rules = [r.strip() for r in result.stdout.split("\n") if r.strip()]

        except Exception as e:
            self.logger.error(f"List rules failed: {e}")

        return rules


class ASTGrepPatterns:
    """Common AST-grep patterns for various languages."""

    @staticmethod
    def console_log() -> str:
        """Pattern for console.log statements."""
        return "console.log($ARG)"

    @staticmethod
    def todo_comment() -> str:
        """Pattern for TODO comments."""
        return "TODO"

    @staticmethod
    def unused_import() -> str:
        """Pattern for unused imports (TypeScript)."""
        return "import $NAME from '$PATH'"

    @staticmethod
    def console_error() -> str:
        """Pattern for console.error statements."""
        return "console.error($ARG)"

    @staticmethod
    def hardcoded_password() -> str:
        """Pattern for hardcoded passwords."""
        return "password = '$VALUE'"

    @staticmethod
    def any_function_call(name: str) -> str:
        """Pattern for any function call."""
        return f"{name}($ARGS)"


ast_grep = ASTGrep()
