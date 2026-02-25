from unittest.mock import MagicMock

import pytest


async def _run_code(code: str) -> str:
    """Helper to run code via CodeModeToolset with no inner tools."""
    from naraninyeo.application.toolsets.code_mode import CodeModeToolset
    from pydantic_ai.toolsets.function import FunctionToolset

    empty_toolset: FunctionToolset = FunctionToolset()
    toolset = CodeModeToolset(empty_toolset)

    ctx = MagicMock()
    ctx.deps = MagicMock()
    ctx.retries = {}
    tool_map = await toolset.get_tools(ctx)
    tool = tool_map["execute_code"]
    return await toolset.call_tool("execute_code", {"code": code}, ctx, tool)


@pytest.mark.asyncio
async def test_execute_python_code_calculation():
    result = await _run_code("1 + 1")
    assert "Result: 2" in result


@pytest.mark.asyncio
async def test_execute_python_code_with_print():
    result = await _run_code("print('hello world')\n10 * 2")
    assert "Result: 20" in result
    assert "STDOUT:" in result
    assert "hello world" in result


@pytest.mark.asyncio
async def test_execute_python_code_syntax_error():
    result = await _run_code("if True")  # Syntax error
    assert "Error:" in result


@pytest.mark.asyncio
async def test_execute_python_code_runtime_error():
    result = await _run_code("1 / 0")  # Runtime error
    assert "Error:" in result
    assert "division by zero" in result.lower()


@pytest.mark.asyncio
async def test_execute_python_code_complex_logic():
    code = """
def fib(n):
    if n <= 1: return n
    return fib(n-1) + fib(n-2)

fib(10)
"""
    result = await _run_code(code)
    assert "Result: 55" in result
