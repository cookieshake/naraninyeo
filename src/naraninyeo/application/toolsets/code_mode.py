from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any, Literal

import pydantic_monty
from pydantic_core import SchemaValidator, core_schema

from pydantic_ai._run_context import AgentDepsT, RunContext
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets.abstract import AbstractToolset, ToolsetTool
from pydantic_ai.toolsets.function import FunctionToolset


@dataclass(kw_only=True)
class _ExecuteCodeTool(ToolsetTool[AgentDepsT]):
    """Minimal ToolsetTool for the execute_code tool."""


def _build_execute_code_validator() -> SchemaValidator:
    return SchemaValidator(
        core_schema.typed_dict_schema(
            {
                "code": core_schema.typed_dict_field(core_schema.str_schema()),
            }
        )
    )


def _json_schema_to_stub(name: str, tool_def: ToolDefinition) -> str:
    """Generate a rough Python stub line for a tool function from its ToolDefinition."""
    schema = tool_def.parameters_json_schema
    props: dict[str, Any] = schema.get("properties", {})
    required: set[str] = set(schema.get("required", []))

    params = []
    for param_name, param_schema in props.items():
        py_type = _schema_to_pytype(param_schema)
        if param_name in required:
            params.append(f"{param_name}: {py_type}")
        else:
            params.append(f"{param_name}: {py_type} = ...")

    param_str = ", ".join(params)
    return_type = "str"
    description = tool_def.description or ""
    stub = f"async def {name}({param_str}) -> {return_type}: ..."
    if description:
        stub = f'async def {name}({param_str}) -> {return_type}:\n    """{description}"""\n    ...'
    return stub


def _schema_to_pytype(schema: dict[str, Any]) -> str:
    t = schema.get("type")
    if t == "string":
        enum = schema.get("enum")
        if enum:
            return "str"  # Literal types are complex; simplify to str
        return "str"
    elif t == "integer":
        return "int"
    elif t == "number":
        return "float"
    elif t == "boolean":
        return "bool"
    elif t == "array":
        items = schema.get("items", {})
        return f"list[{_schema_to_pytype(items)}]"
    elif t == "object":
        return "dict"
    elif "anyOf" in schema:
        types = [_schema_to_pytype(s) for s in schema["anyOf"]]
        return " | ".join(types)
    return "Any"


class CodeModeToolset(AbstractToolset[AgentDepsT]):
    """A toolset that presents a single 'execute_code' tool to the LLM.

    The LLM writes Python code that calls the wrapped toolset's functions
    directly. pydantic_monty executes the code safely, dispatching external
    function calls back to the real implementations.
    """

    def __init__(self, wrapped: FunctionToolset[AgentDepsT], *, id: str | None = None) -> None:
        self._wrapped = wrapped
        self._id = id
        self._validator = _build_execute_code_validator()

    @property
    def id(self) -> str | None:
        return self._id

    async def get_tools(self, ctx: RunContext[AgentDepsT]) -> dict[str, ToolsetTool[AgentDepsT]]:
        inner_tools = await self._wrapped.get_tools(ctx)

        # Build a description that lists all available functions with stubs
        stubs = []
        for name, tool in inner_tools.items():
            stubs.append(_json_schema_to_stub(name, tool.tool_def))
        stubs_str = "\n\n".join(stubs)

        description = (
            "Python 코드를 안전한 샌드박스에서 실행하는 도구입니다.\n"
            "아래 함수들을 코드에서 직접 호출할 수 있습니다:\n\n"
            f"```python\n{stubs_str}\n```\n\n"
            "코드의 마지막 표현식 값이 결과로 반환됩니다. print() 출력도 캡처됩니다.\n"
            "외부 네트워크/파일시스템 접근은 위 함수들을 통해서만 가능합니다."
        )

        tool_def = ToolDefinition(
            name="execute_code",
            description=description,
            parameters_json_schema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "실행할 Python 코드",
                    }
                },
                "required": ["code"],
            },
        )

        return {
            "execute_code": _ExecuteCodeTool(
                toolset=self,
                tool_def=tool_def,
                max_retries=1,
                args_validator=self._validator,
            )
        }

    async def call_tool(
        self,
        name: str,  # noqa: ARG002
        tool_args: dict[str, Any],
        ctx: RunContext[AgentDepsT],
        tool: ToolsetTool[AgentDepsT],  # noqa: ARG002
    ) -> Any:
        code: str = tool_args["code"]
        inner_tools = await self._wrapped.get_tools(ctx)
        tool_names = list(inner_tools.keys())

        stdout_parts: list[str] = []

        def print_callback(_stream: Literal["stdout"], text: str) -> None:
            stdout_parts.append(text)

        async def make_caller(t_name: str, t_tool: ToolsetTool[AgentDepsT]):
            async def caller(*args: Any, **kwargs: Any) -> Any:
                # Build tool_args from positional + keyword args using the schema
                props = t_tool.tool_def.parameters_json_schema.get("properties", {})
                param_names = list(props.keys())
                merged: dict[str, Any] = {}
                for i, val in enumerate(args):
                    if i < len(param_names):
                        merged[param_names[i]] = val
                merged.update(kwargs)
                result = await self._wrapped.call_tool(t_name, merged, ctx, t_tool)
                return result

            return caller

        external_functions: dict[str, Any] = {}
        for t_name, t_tool in inner_tools.items():
            external_functions[t_name] = await make_caller(t_name, t_tool)

        try:
            m = pydantic_monty.Monty(
                code,
                external_functions=tool_names,
            )
            result = await pydantic_monty.run_monty_async(
                m,
                external_functions=external_functions,
                print_callback=print_callback,
            )

            output_parts = []
            stdout_content = "".join(stdout_parts).strip()
            if stdout_content:
                output_parts.append(f"STDOUT:\n{stdout_content}")
            if result is not None:
                output_parts.append(f"Result: {result}")

            return "\n".join(output_parts) if output_parts else "Code executed successfully (no result)"

        except pydantic_monty.MontyError as e:
            error_msg = e.display() if hasattr(e, "display") else str(e)  # type: ignore
            return f"Error:\n```\n{error_msg}\n```"
        except Exception:
            return f"Error:\n```\n{traceback.format_exc()}\n```"
