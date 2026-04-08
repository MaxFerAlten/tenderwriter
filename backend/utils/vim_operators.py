"""Vim operators implementation for backend."""

from typing import Dict, Callable, Any, Optional

State = Dict[str, Any]


def delete_char(state: State) -> str:
    line = state["line"]
    position = state["position"]
    return line[:position] + line[position + 1:]


def delete_word(state: State) -> str:
    """Delete word at position (Vim dw)."""
    line = state["line"]
    position = state["position"]
    
    # Skip leading spaces
    start = position
    while start < len(line) and line[start] == " ":
        start += 1
    
    # Find end of word
    end = start
    while end < len(line) and line[end] not in " \t\n":
        end += 1
    
    # Skip trailing space after word (Vim dw behavior)
    if end < len(line) and line[end] == " ":
        end += 1
    
    return line[:position] + line[end:]


def yank_line(state: State) -> str:
    return state["line"]


def change_char(state: State) -> str:
    line = state["line"]
    position = state["position"]
    return line[:position] + line[position + 1:]


def put_after(state: State) -> str:
    registers = state.get("registers", {})
    reg = registers.get("", "")
    line = state["line"]
    position = state["position"]
    return line[:position + 1] + reg + line[position + 1:]


OPERATORS: Dict[str, Callable[[State, Optional[str]], str]] = {
    "d": lambda state, motion: delete_word(state) if motion == "w" else delete_char(state),
    "y": lambda state, motion: yank_line(state),
    "c": lambda state, motion: change_char(state),
    "x": lambda state, motion: delete_char(state),
    "p": lambda state, motion: put_after(state),
}


def execute_operator(op: str, state: State, motion: Optional[str] = None) -> str:
    fn = OPERATORS.get(op)
    if fn:
        return fn(state, motion)
    return state["line"]