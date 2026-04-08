"""LSP (Language Server Protocol) tools for TenderClaw."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LSPLocation:
    """Represents a location in a file."""
    file_path: str
    line: int
    column: int = 0


@dataclass
class LSPDiagnostic:
    """Represents a diagnostic (error/warning)."""
    file_path: str
    line: int
    column: int
    severity: str
    message: str
    source: str | None = None


class LSPClient:
    """Base LSP client for language server communication."""

    def __init__(self, server_command: list[str], cwd: str | None = None):
        self.command = server_command
        self.cwd = cwd
        self.process: subprocess.Popen | None = None
        self.logger = logging.getLogger(f"{__name__}.LSPClient")
        self._request_id = 0

    def start(self) -> None:
        """Start the LSP server."""
        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.cwd,
                text=False
            )
            self.logger.info(f"Started LSP server: {' '.join(self.command)}")
        except Exception as e:
            self.logger.error(f"Failed to start LSP server: {e}")
            raise

    def stop(self) -> None:
        """Stop the LSP server."""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None

    def send_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a request to the LSP server."""
        if not self.process:
            raise RuntimeError("LSP server not running")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {}
        }

        request_json = json.dumps(request) + "\n"
        self.process.stdin.write(request_json.encode())
        self.process.stdin.flush()

        response_line = self.process.stdout.readline()
        if not response_line:
            return {}

        response = json.loads(response_line.decode())
        return response.get("result", {})

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class LSPTools:
    """Collection of LSP-based tools."""

    def __init__(self, lsp_client: LSPClient | None = None):
        self.client = lsp_client
        self.logger = logging.getLogger(f"{__name__}.LSPTools")

    def goto_definition(self, file_path: str, line: int, column: int) -> LSPLocation | None:
        """
        Go to symbol definition.
        
        Args:
            file_path: File path
            line: Line number (1-indexed)
            column: Column number
            
        Returns:
            Location of definition or None
        """
        if not self.client:
            return None

        try:
            result = self.client.send_request("textDocument/definition", {
                "textDocument": {"uri": f"file://{file_path}"},
                "position": {"line": line - 1, "character": column}
            })

            if result and "uri" in result:
                uri = result["uri"]
                location = result.get("range", {}).get("start", {})
                return LSPLocation(
                    file_path=uri.replace("file://", ""),
                    line=location.get("line", 0) + 1,
                    column=location.get("character", 0)
                )
        except Exception as e:
            self.logger.error(f"Goto definition failed: {e}")

        return None

    def find_references(
        self,
        file_path: str,
        line: int,
        column: int,
        include_declaration: bool = True
    ) -> list[LSPLocation]:
        """
        Find all references to a symbol.
        
        Args:
            file_path: File path
            line: Line number (1-indexed)
            column: Column number
            include_declaration: Include the declaration itself
            
        Returns:
            List of reference locations
        """
        if not self.client:
            return []

        locations = []
        try:
            result = self.client.send_request("textDocument/references", {
                "textDocument": {"uri": f"file://{file_path}"},
                "position": {"line": line - 1, "character": column},
                "context": {"includeDeclaration": include_declaration}
            })

            for ref in result:
                uri = ref.get("uri", "")
                location = ref.get("range", {}).get("start", {})
                locations.append(LSPLocation(
                    file_path=uri.replace("file://", ""),
                    line=location.get("line", 0) + 1,
                    column=location.get("character", 0)
                ))
        except Exception as e:
            self.logger.error(f"Find references failed: {e}")

        return locations

    def rename(
        self,
        file_path: str,
        line: int,
        column: int,
        new_name: str
    ) -> dict[str, list[LSPLocation]]:
        """
        Rename a symbol across the workspace.
        
        Args:
            file_path: File path
            line: Line number (1-indexed)
            column: Column number
            new_name: New symbol name
            
        Returns:
            Dictionary of file_path -> list of changes
        """
        if not self.client:
            return {}

        changes = {}
        try:
            result = self.client.send_request("workspace/rename", {
                "textDocument": {"uri": f"file://{file_path}"},
                "position": {"line": line - 1, "character": column},
                "newName": new_name
            })

            if result and "documentChanges" in result:
                for change in result["documentChanges"]:
                    if "textDocument" in change:
                        uri = change["textDocument"]["uri"]
                        fp = uri.replace("file://", "")
                        changes[fp] = [
                            LSPLocation(
                                file_path=fp,
                                line=edit["range"]["start"]["line"] + 1,
                                column=edit["range"]["start"]["character"]
                            )
                            for edit in change.get("edits", [])
                        ]
        except Exception as e:
            self.logger.error(f"Rename failed: {e}")

        return changes

    def get_diagnostics(self, file_path: str) -> list[LSPDiagnostic]:
        """
        Get diagnostics for a file.
        
        Args:
            file_path: File path
            
        Returns:
            List of diagnostics
        """
        if not self.client:
            return []

        diagnostics = []
        try:
            result = self.client.send_request("textDocument/diagnostic", {
                "textDocument": {"uri": f"file://{file_path}"}
            })

            items = result.get("items", []) if isinstance(result, dict) else result

            for diag in items:
                location = diag.get("range", {}).get("start", {})
                diagnostics.append(LSPDiagnostic(
                    file_path=file_path,
                    line=location.get("line", 0) + 1,
                    column=location.get("character", 0),
                    severity=diag.get("severity", "error"),
                    message=diag.get("message", ""),
                    source=diag.get("source")
                ))
        except Exception as e:
            self.logger.error(f"Get diagnostics failed: {e}")

        return diagnostics

    def get_document_symbols(self, file_path: str) -> list[dict[str, Any]]:
        """
        Get symbols defined in a document.
        
        Args:
            file_path: File path
            
        Returns:
            List of symbol information
        """
        if not self.client:
            return []

        symbols = []
        try:
            result = self.client.send_request("textDocument/documentSymbol", {
                "textDocument": {"uri": f"file://{file_path}"}
            })

            for symbol in result:
                location = symbol.get("location", {}).get("range", {}).get("start", {})
                symbols.append({
                    "name": symbol.get("name", ""),
                    "kind": symbol.get("kind", 0),
                    "file_path": file_path,
                    "line": location.get("line", 0) + 1,
                    "column": location.get("character", 0)
                })
        except Exception as e:
            self.logger.error(f"Get document symbols failed: {e}")

        return symbols
