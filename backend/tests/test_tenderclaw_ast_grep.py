"""Tests for AST-grep tools."""

import pytest

from backend.tools.ast_grep.search import (
    ASTGrep,
    ASTGrepPatterns,
    ASTMatch,
    ASTReplacement,
)


class TestASTMatch:
    """Tests for AST match."""

    def test_create_match(self):
        """Test creating an AST match."""
        match = ASTMatch(
            file_path="test.ts",
            line=10,
            column=5,
            matched_content="console.log(x)"
        )
        assert match.file_path == "test.ts"
        assert match.line == 10
        assert match.column == 5
        assert match.matched_content == "console.log(x)"


class TestASTReplacement:
    """Tests for AST replacement."""

    def test_create_replacement(self):
        """Test creating a replacement."""
        match = ASTMatch(
            file_path="test.ts",
            line=10,
            column=5,
            matched_content="console.log(x)"
        )
        replacement = ASTReplacement(
            file_path="test.ts",
            matches=[match],
            new_content="logger.info(x)"
        )
        assert replacement.file_path == "test.ts"
        assert len(replacement.matches) == 1
        assert replacement.new_content == "logger.info(x)"


class TestASTGrep:
    """Tests for AST-grep."""

    def test_search_no_binary(self):
        """Test search when ast-grep is not available."""
        grep = ASTGrep(binary_path="nonexistent-ast-grep")
        results = grep.search("console.log($ARG)")
        
        assert results == []

    def test_replace_no_binary(self):
        """Test replace when ast-grep is not available."""
        grep = ASTGrep(binary_path="nonexistent-ast-grep")
        results = grep.replace(
            "console.log($ARG)",
            "logger.info($ARG)"
        )
        
        assert "errors" in results
        assert len(results["errors"]) > 0

    def test_list_rules_no_binary(self):
        """Test list rules when ast-grep is not available."""
        grep = ASTGrep(binary_path="nonexistent-ast-grep")
        rules = grep.list_rules()
        
        assert rules == []


class TestASTGrepPatterns:
    """Tests for common AST-grep patterns."""

    def test_console_log_pattern(self):
        """Test console.log pattern."""
        pattern = ASTGrepPatterns.console_log()
        assert "console.log" in pattern

    def test_todo_comment_pattern(self):
        """Test TODO comment pattern."""
        pattern = ASTGrepPatterns.todo_comment()
        assert "TODO" in pattern

    def test_any_function_call_pattern(self):
        """Test any function call pattern."""
        pattern = ASTGrepPatterns.any_function_call("foo")
        assert "foo" in pattern
