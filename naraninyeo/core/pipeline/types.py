from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from naraninyeo.core.models.message import Message
from naraninyeo.core.models.reply import ReplyContext
from naraninyeo.core.models.retrieval import RetrievalPlan, RetrievalResult

EmitFn = Callable[[Message], Awaitable[None]]


@dataclass
class PipelineState:
    """Mutable state shared by pipeline steps."""

    incoming: Message
    history: list[Message] | None = None
    reply_needed: Optional[bool] = None
    reply_context: ReplyContext | None = None
    plans: list[RetrievalPlan] | None = None
    retrieval_results: list[RetrievalResult] | None = None
    stop: bool = False
    finalizers: list[asyncio.Task[Any]] = field(default_factory=list)
