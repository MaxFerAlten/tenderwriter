"""Tests for LSP tools."""

import pytest

from backend.tools.lsp.client import LSPDiagnostic, LSPLocation, LSPTools


class TestLSPLocation:
    """Tests for LSP location."""

    def test_create_location(self):
        """Test creating a location."""
        loc = LSPLocation(file_path="test.ts", line=10, column=5)
        assert loc.file_path == "test.ts"
        assert loc.line == 10
        assert loc.column == 5

    def test_location_defaults(self):
        """Test location default values."""
        loc = LSPLocation(file_path="test.ts", line=1)
        assert loc.column == 0


class TestLSPDiagnostic:
    """Tests for LSP diagnostic."""

    def test_create_diagnostic(self):
        """Test creating a diagnostic."""
        diag = LSPDiagnostic(
            file_path="test.ts",
            line=10,
            column=5,
            severity="error",
            message="Unexpected token"
        )
        assert diag.file_path == "test.ts"
        assert diag.severity == "error"
        assert diag.message == "Unexpected token"


class TestLSPTools:
    """Tests for LSP tools."""

    def test_goto_definition_no_client(self):
        """Test goto definition without client."""
        tools = LSPTools(lsp_client=None)
        result = tools.goto_definition("test.ts", 1, 0)
        
        assert result is None

    def test_find_references_no_client(self):
        """Test find references without client."""
        tools = LSPTools(lsp_client=None)
        result = tools.find_references("test.ts", 1, 0)
        
        assert result == []

    def test_rename_no_client(self):
        """Test rename without client."""
        tools = LSPTools(lsp_client=None)
        result = tools.rename("test.ts", 1, 0, "newName")
        
        assert result == {}

    def test_get_diagnostics_no_client(self):
        """Test get diagnostics without client."""
        tools = LSPTools(lsp_client=None)
        result = tools.get_diagnostics("test.ts")
        
        assert result == []

    def test_get_document_symbols_no_client(self):
        """Test get document symbols without client."""
        tools = LSPTools(lsp_client=None)
        result = tools.get_document_symbols("test.ts")
        
        assert result == []
