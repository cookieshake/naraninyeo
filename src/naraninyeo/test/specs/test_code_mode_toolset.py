"""
CodeModeToolset 행동 스펙 테스트

스펙:
- 유효한 Python 코드 → 실행 결과 반환
- print 출력 → STDOUT에 캡처되어 반환
- 문법/런타임 에러 → "Error:" 접두사 에러 메시지 반환
- 등록된 tool 함수를 코드 내에서 호출 가능
연동: 없음 (pydantic-monty 샌드박스 자체 실행)
"""

from unittest.mock import MagicMock

import pytest
from pydantic_ai.toolsets.function import FunctionToolset

from naraninyeo.toolsets.code_mode import CodeModeToolset


async def _run_code(code: str) -> str:
    toolset = CodeModeToolset(FunctionToolset())
    ctx = MagicMock()
    ctx.deps = MagicMock()
    ctx.retries = {}
    tool_map = await toolset.get_tools(ctx)
    tool = tool_map["execute_code"]
    return await toolset.call_tool("execute_code", {"code": code}, ctx, tool)


@pytest.mark.asyncio
async def test_valid_expression_returns_result():
    """유효한 표현식은 결과를 반환한다."""
    result = await _run_code("1 + 1")

    assert "Result: 2" in result


@pytest.mark.asyncio
async def test_print_output_is_captured():
    """print 출력이 STDOUT으로 캡처된다."""
    result = await _run_code("print('hello world')\n10 * 2")

    assert "STDOUT:" in result
    assert "hello world" in result
    assert "Result: 20" in result


@pytest.mark.asyncio
async def test_syntax_error_returns_error_message():
    """문법 에러 시 'Error:' 접두사 메시지를 반환한다."""
    result = await _run_code("if True")  # 문법 에러

    assert "Error:" in result


@pytest.mark.asyncio
async def test_runtime_error_returns_error_message():
    """런타임 에러 시 'Error:' 접두사 메시지를 반환한다."""
    result = await _run_code("1 / 0")

    assert "Error:" in result
    assert "division by zero" in result.lower()


@pytest.mark.asyncio
async def test_complex_logic_executes_correctly():
    """복잡한 로직도 올바르게 실행된다."""
    code = """
def fib(n):
    if n <= 1: return n
    return fib(n-1) + fib(n-2)

fib(10)
"""
    result = await _run_code(code)

    assert "Result: 55" in result


