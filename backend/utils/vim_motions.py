"""Vim motions implementation for backend."""

from typing import Dict, Callable, Any

State = Dict[str, Any]


def word_end(text: str, pos: int) -> int:
    length = len(text)
    while pos < length and not text[pos].isspace():
        pos += 1
    while pos < length and text[pos].isspace():
        pos += 1
    return min(pos, length)


def word_start(text: str, pos: int) -> int:
    while pos > 0 and text[pos - 1].isspace():
        pos -= 1
    while pos > 0 and not text[pos - 1].isspace():
        pos -= 1
    return pos


def line_start(text: str, _pos: int) -> int:
    return 0


def line_end(text: str, pos: int) -> int:
    newline = text.find("\n")
    if newline == -1:
        return len(text)
    return newline


def char_forward(state: State) -> int:
    pos = state["position"]
    text = state["line"]
    return min(pos + 1, len(text))


def char_backward(state: State) -> int:
    pos = state["position"]
    return max(pos - 1, 0)


def word_end_motion(state: State) -> int:
    return word_end(state["line"], state["position"])


def word_start_motion(state: State) -> int:
    return word_start(state["line"], state["position"])


def word_end_minus_one(state: State) -> int:
    end = word_end(state["line"], state["position"])
    return end - 1 if end > 0 else 0


def line_start_of_line(state: State) -> int:
    return 0


def first_non_whitespace(state: State) -> int:
    line = state["line"]
    for i, char in enumerate(line):
        if not char.isspace():
            return i
    return len(line)


def line_end_of_line(state: State) -> int:
    return line_end(state["line"], state["position"])


def goto_line_start(state: State) -> int:
    return 0


def goto_line_end(state: State) -> int:
    return len(state["line"])


MOTIONS: Dict[str, Callable[[State], int]] = {
    "h": char_backward,
    "arrowleft": char_backward,
    "l": char_forward,
    "arrowright": char_forward,
    "w": word_end_motion,
    "b": word_start_motion,
    "e": word_end_minus_one,
    "0": line_start_of_line,
    "^": first_non_whitespace,
    "$": line_end_of_line,
    "gg": goto_line_start,
    "G": goto_line_end,
}


def execute_motion(motion: str, state: State) -> int:
    fn = MOTIONS.get(motion)
    if fn:
        return fn(state)
    return state["position"]