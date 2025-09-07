from __future__ import annotations

from typing import Callable, Sequence, TypeVar, cast

from pydantic_ai import NativeOutput, PromptedOutput, TextOutput, ToolOutput
from pydantic_ai.output import OutputSpec

T = TypeVar("T")


def text() -> OutputSpec[str]:
    """Text output (streaming-friendly)."""
    return str


def native(tp: type[T]) -> OutputSpec[T]:
    """Prefer native JSON-schema output for a single type.

    Use this only if your model/provider supports native JSON-schema output.
    """
    return NativeOutput(tp)


def tool(
    tp: type[T],
    *,
    name: str | None = None,
    description: str | None = None,
    strict: bool | None = None,
) -> OutputSpec[T]:
    """Force tool-based structured output for a single type."""
    return ToolOutput(tp, name=name, description=description, strict=strict)


def prompted(outputs: Sequence[type[T]], *, name: str | None = None, description: str | None = None) -> OutputSpec[T]:
    """Prompted structured output from one-or-more types.

    This allows you to guide the model to choose a type without JSON schema support.
    """
    return PromptedOutput(list(outputs), name=name, description=description)


def list_of(tp: type[T]) -> OutputSpec[list[T]]:
    """Typed helper to express `list[T]` as an OutputSpec for static type checkers.

    Pylance can be strict about `output_type` expecting an `OutputSpec[T]`.
    Using `list[T]` directly may trip overload resolution, so this function
    helps by returning a value typed as `OutputSpec[list[T]]` while preserving
    the runtime behavior.
    """
    return cast(OutputSpec[list[T]], list[tp])


def union_of(*types: type[T]) -> OutputSpec[T]:
    """Union of multiple output types, expressed as an OutputSpec.

    Example:
      spec = union_of(Fruit, Vehicle)
    """
    return cast(OutputSpec[T], list(types))


def text_fn(fn: Callable[[str], T]) -> OutputSpec[T]:
    """Process plain text via a function `str -> T`.

    Equivalent to `TextOutput(fn)`.
    """
    return TextOutput(fn)
