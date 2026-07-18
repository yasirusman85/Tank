import json
from dataclasses import dataclass
from functools import singledispatch
from typing import AsyncGenerator, Any, Optional
from starlette.responses import StreamingResponse

from tank.ai.agents import (
    AgentStep,
    ThoughtStep,
    ToolCallStep,
    ToolResponseStep,
    TextTokenStep,
    FinalResponseStep,
    ValidationErrorStep,
    ApprovalRequiredStep,
)


@dataclass(frozen=True)
class SSEEvent:
    name: str
    data: dict[str, Any]


@singledispatch
def _step_to_event(step: AgentStep) -> Optional[SSEEvent]:
    return None


@_step_to_event.register
def _(step: ThoughtStep) -> SSEEvent:
    return SSEEvent(name="thought", data={"thought": step.thought})


@_step_to_event.register
def _(step: ToolCallStep) -> SSEEvent:
    return SSEEvent(
        name="tool_call",
        data={"name": step.name, "arguments": step.arguments, "id": step.id},
    )


@_step_to_event.register
def _(step: ToolResponseStep) -> SSEEvent:
    return SSEEvent(
        name="tool_response",
        data={"name": step.name, "result": step.result, "id": step.id},
    )


@_step_to_event.register
def _(step: TextTokenStep) -> SSEEvent:
    return SSEEvent(name="token", data={"token": step.token})


@_step_to_event.register
def _(step: FinalResponseStep) -> SSEEvent:
    return SSEEvent(name="done", data={"text": step.text})


@_step_to_event.register
def _(step: ValidationErrorStep) -> SSEEvent:
    return SSEEvent(name="validation_error", data={"errors": step.errors})


@_step_to_event.register
def _(step: ApprovalRequiredStep) -> SSEEvent:
    return SSEEvent(
        name="approval_required",
        data={"tool_name": step.tool_name, "arguments": step.arguments, "id": step.id},
    )


class AgentStepEventFactory:
    """Factory for converting agent steps into SSE events."""

    @staticmethod
    def create(step: AgentStep) -> Optional[SSEEvent]:
        return _step_to_event(step)

class AgentStreamResponse(StreamingResponse):
    """
    Extends Starlette's StreamingResponse to stream Agent execution steps
    formatted as Server-Sent Events (SSE).
    """
    def __init__(self, steps_generator: AsyncGenerator[AgentStep, None], **kwargs):
        async def sse_iterator() -> AsyncGenerator[bytes, None]:
            async for step in steps_generator:
                event = AgentStepEventFactory.create(step)
                if event:
                    data_str = json.dumps(event.data)
                    sse_message = f"event: {event.name}\ndata: {data_str}\n\n"
                    yield sse_message.encode("utf-8")

        headers = kwargs.pop("headers", {})
        headers.setdefault("Content-Type", "text/event-stream")
        headers.setdefault("Cache-Control", "no-cache")
        headers.setdefault("Connection", "keep-alive")
        headers.setdefault("X-Accel-Buffering", "no")

        super().__init__(
            content=sse_iterator(),
            status_code=200,
            headers=headers,
            media_type="text/event-stream",
            **kwargs
        )
