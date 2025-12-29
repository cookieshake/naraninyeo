import logging

from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime

from naraninyeo.api.agents.profanity_checker import ProfanityCheckerDeps, profanity_checker
from naraninyeo.api.graphs.new_message.models import (
    NewMessageGraphContext,
    NewMessageGraphState,
)


async def check_profanity(
    state: NewMessageGraphState, runtime: Runtime[NewMessageGraphContext]
) -> NewMessageGraphState:
    logging.info("Checking profanity")

    deps = ProfanityCheckerDeps(
        incoming_message=state.incoming_message,
    )

    result = await profanity_checker.run_with_generator(deps)
    state.is_profane = result.output.is_profane
    state.profanity_reason = result.output.reason

    if state.is_profane:
        logging.info(f"Profanity detected: {state.profanity_reason}")
        state.status = "completed"

        writer = get_stream_writer()
        writer(
            {
                "type": "response",
                "text": f"부적절한 언어나 요청 감지.\n({state.profanity_reason})",
            }
        )

    return state
