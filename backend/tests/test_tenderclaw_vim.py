"""Tests for Vim mode utilities."""

import pytest
from backend.utils.vim_motions import execute_motion, MOTIONS
from backend.utils.vim_operators import execute_operator, OPERATORS


class TestMotions:
    def test_char_forward(self):
        state = {"line": "hello", "position": 2}
        assert execute_motion("l", state) == 3

    def test_char_backward(self):
        state = {"line": "hello", "position": 2}
        assert execute_motion("h", state) == 1

    def test_line_end(self):
        state = {"line": "hello\nworld", "position": 0}
        assert execute_motion("$", state) == 5

    def test_line_start(self):
        state = {"line": "  hello", "position": 5}
        assert execute_motion("0", state) == 0

    def test_word_forward(self):
        state = {"line": "hello world", "position": 0}
        assert execute_motion("w", state) == 6

    def test_word_backward(self):
        state = {"line": "hello world", "position": 6}
        assert execute_motion("b", state) == 0


class TestOperators:
    def test_delete_char(self):
        state = {"line": "hello", "position": 2}
        assert execute_operator("x", state) == "helo"

    def test_delete_word(self):
        state = {"line": "hello world", "position": 0}
        result = execute_operator("d", state, "w")
        assert result == "world"

    def test_yank(self):
        state = {"line": "hello world", "position": 0}
        assert execute_operator("y", state) == "hello world"

    def test_change(self):
        state = {"line": "hello", "position": 2}
        assert execute_operator("c", state) == "helo"