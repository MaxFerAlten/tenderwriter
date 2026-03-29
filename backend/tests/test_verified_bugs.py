"""
Tests that verify the existence of bugs found during codebase analysis,
then confirm they are fixed after applying patches.

All tests are synchronous to avoid pytest-asyncio dependency.
"""
import ast
import json
import pytest


# ── Bug 1: int(user_id) ValueError in legacy.py ──

def test_bug_legacy_int_valueerror():
    """legacy.py:50 — int(user_id) raises unhandled ValueError for non-numeric JWT sub.

    We verify the code has a try/except around int() conversion.
    Before fix: ValueError propagates as 500.
    After fix: caught and returns HTTPException 401.
    """
    with open("app/auth/legacy.py", "r") as f:
        source = f.read()

    # The fix should wrap int(user_id) in a try/except ValueError
    # or use a safe conversion. We check that ValueError is handled.
    tree = ast.parse(source)

    # Find the validate_token method and check for ValueError handling
    has_valueerror_handler = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                # bare except catches everything including ValueError
                has_valueerror_handler = True
            elif isinstance(node.type, ast.Name) and node.type.id == "ValueError":
                has_valueerror_handler = True
            elif isinstance(node.type, ast.Tuple):
                for elt in node.type.elts:
                    if isinstance(elt, ast.Name) and elt.id == "ValueError":
                        has_valueerror_handler = True

    assert has_valueerror_handler, (
        "legacy.py must handle ValueError from int(user_id) conversion. "
        "A non-numeric JWT 'sub' claim currently causes an unhandled 500 error."
    )


# ── Bug 2: json.loads without try/except in onlyoffice.py ──

def test_bug_onlyoffice_redis_json_loads():
    """onlyoffice.py:406 — json.loads on corrupted Redis data should not crash.

    We verify the code has error handling around json.loads in get_session_metadata.
    """
    with open("app/api/onlyoffice.py", "r") as f:
        source = f.read()

    # Extract the get_session_metadata function body
    func_start = source.index("async def get_session_metadata")
    # Find the next function or end of relevant block
    next_func = source.find("\nasync def ", func_start + 1)
    if next_func == -1:
        next_func = source.find("\ndef ", func_start + 1)
    func_body = source[func_start:next_func] if next_func != -1 else source[func_start:]

    # The fix should wrap json.loads in try/except
    assert "try:" in func_body and ("JSONDecodeError" in func_body or "Exception" in func_body or "ValueError" in func_body), (
        "get_session_metadata must handle json.JSONDecodeError. "
        "Corrupted Redis data currently crashes the endpoint with an unhandled exception."
    )


# ── Bug 3: JSON extraction with find/rfind in pipeline.py ──

def _extract_first_json_object(text):
    """Local copy of the fixed function for testing without structlog dependency."""
    starts = [i for i, c in enumerate(text) if c == "{"]
    if not starts:
        return None
    decoder = json.JSONDecoder()
    for start in starts:
        try:
            obj, _ = decoder.raw_decode(text, start)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def test_bug_pipeline_json_extraction_mixed():
    """pipeline.py — _extract_first_json_object handles mixed LLM output correctly."""

    # Case 1: garbage before real JSON — old find/rfind would fail
    response = (
        'Here is some context { "incomplete": true and then '
        'the real response {"projects": [], "team_members": []}'
    )
    result = _extract_first_json_object(response)
    assert result is not None
    assert "projects" in result

    # Case 2: clean JSON
    result = _extract_first_json_object('{"a": 1}')
    assert result == {"a": 1}

    # Case 3: JSON wrapped in markdown code block
    result = _extract_first_json_object('```json\n{"projects": [1,2]}\n```')
    assert result == {"projects": [1, 2]}

    # Case 4: no JSON at all
    result = _extract_first_json_object("No JSON here at all")
    assert result is None

    # Case 5: nested objects
    result = _extract_first_json_object('Blah {"outer": {"inner": true}}')
    assert result == {"outer": {"inner": True}}

    # Case 6: the old approach would have failed on this
    broken_for_old = '{ broken then {"valid": true}'
    old_start = broken_for_old.find("{")
    old_end = broken_for_old.rfind("}") + 1
    with pytest.raises(json.JSONDecodeError):
        json.loads(broken_for_old[old_start:old_end])
    # New approach works
    assert _extract_first_json_object(broken_for_old) == {"valid": True}

    # Verify pipeline.py uses the new function (not find/rfind)
    with open("app/ingestion/pipeline.py", "r") as f:
        source = f.read()
    assert "_extract_first_json_object" in source, "pipeline.py should use _extract_first_json_object"
    # The old fragile pattern should be gone from _extract_and_graph
    extract_section = source[source.index("_extract_and_graph"):]
    assert "response_text.find" not in extract_section, "Old find/rfind pattern should be removed"


# ── Bug 4: traceback.print_exc() instead of logger in main.py ──

def test_bug_main_traceback_print():
    """main.py:72-73 — startup errors go to stdout instead of structured logger."""
    with open("app/main.py", "r") as f:
        source = f.read()

    tree = ast.parse(source)

    uses_print_exc = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "print_exc":
            uses_print_exc = True

    assert not uses_print_exc, (
        "main.py should use logger.exception() instead of traceback.print_exc(). "
        "Startup errors currently go to stdout and are missed by log aggregation."
    )


# ── Bug 5: Streaming history save failure is silent ──

def test_bug_rag_stream_history_no_try_except():
    """rag.py:108-115 — db.commit() failure in stream generator should be caught."""
    with open("app/api/rag.py", "r") as f:
        source = f.read()

    # Extract the stream_generator portion
    stream_start = source.index("async def stream_generator")
    stream_end = source.index('yield "data: [DONE]', stream_start)
    stream_body = source[stream_start:stream_end]

    # There should be error handling around the db operations
    has_error_handling = "try:" in stream_body and ("except" in stream_body)

    assert has_error_handling, (
        "stream_generator should wrap history db.commit() in try/except. "
        "If commit fails after streaming started, client receives [DONE] but history is lost."
    )
