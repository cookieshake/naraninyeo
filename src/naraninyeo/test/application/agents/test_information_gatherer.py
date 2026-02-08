import pytest
from unittest.mock import MagicMock
from pydantic_ai import RunContext
from naraninyeo.application.agents.information_gatherer import (
    execute_python_code,
    InformationGathererDeps,
    InformationGathererOutput,
)

@pytest.fixture
def mock_ctx():
    return MagicMock()

@pytest.mark.asyncio
async def test_execute_python_code_calculation(mock_ctx):
    code = "1 + 1"
    result = await execute_python_code(mock_ctx, code)
    
    assert isinstance(result, InformationGathererOutput)
    assert result.source == "Python Code Execution (Sandbox)"
    assert "Result: 2" in result.content

@pytest.mark.asyncio
async def test_execute_python_code_with_print(mock_ctx):
    code = "print('hello world')\n10 * 2"
    result = await execute_python_code(mock_ctx, code)
    
    assert "Result: 20" in result.content

@pytest.mark.asyncio
async def test_execute_python_code_syntax_error(mock_ctx):
    code = "if True"  # Syntax error
    result = await execute_python_code(mock_ctx, code)
    
    assert "Error:" in result.content

@pytest.mark.asyncio
async def test_execute_python_code_runtime_error(mock_ctx):
    code = "1 / 0"  # Runtime error
    result = await execute_python_code(mock_ctx, code)
    
    assert "Error:" in result.content
    assert "division by zero" in result.content.lower()

@pytest.mark.asyncio
async def test_execute_python_code_complex_logic(mock_ctx):
    code = """
def fib(n):
    if n <= 1: return n
    return fib(n-1) + fib(n-2)

fib(10)
"""
    result = await execute_python_code(mock_ctx, code)
    assert "Result: 55" in result.content