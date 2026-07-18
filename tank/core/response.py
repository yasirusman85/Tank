import json
from typing import AsyncGenerator
from starlette.responses import StreamingResponse

from tank.ai.agents import (
    AgentStep,
    ThoughtStep,
    ToolCallStep,
    ToolResponseStep,
    TextTokenStep,
    FinalResponseStep,
)

class AgentStreamResponse(StreamingResponse):
    """
    Extends Starlette's StreamingResponse to stream Agent execution steps
    formatted as Server-Sent Events (SSE).
    """
    def __init__(self, steps_generator: AsyncGenerator[AgentStep, None], **kwargs):
        async def sse_iterator() -> AsyncGenerator[bytes, None]:
            async for step in steps_generator:
                event_name = None
                data_dict = {}

                if isinstance(step, ThoughtStep):
                    event_name = "thought"
                    data_dict = {"thought": step.thought}
                elif isinstance(step, ToolCallStep):
                    event_name = "tool_call"
                    data_dict = {"name": step.name, "arguments": step.arguments, "id": step.id}
                elif isinstance(step, ToolResponseStep):
                    event_name = "tool_response"
                    data_dict = {"name": step.name, "result": step.result, "id": step.id}
                elif isinstance(step, TextTokenStep):
                    event_name = "token"
                    data_dict = {"token": step.token}
                elif isinstance(step, FinalResponseStep):
                    event_name = "done"
                    data_dict = {"text": step.text}

                if event_name:
                    data_str = json.dumps(data_dict)
                    sse_message = f"event: {event_name}\ndata: {data_str}\n\n"
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
