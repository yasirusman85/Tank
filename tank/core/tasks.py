"""
Async background task queue and worker manager for Tank framework.
Enables running long-running Agent workflows asynchronously without holding open HTTP requests.
"""
import uuid
import time
import asyncio
from typing import Dict, Any, List, Optional
from tank.ai.agents import Agent, FinalResponseStep, ValidationErrorStep


class TaskRecord:
    def __init__(self, task_id: str, agent_name: str, session_id: str, prompt: str):
        self.task_id = task_id
        self.agent_name = agent_name
        self.session_id = session_id
        self.prompt = prompt
        self.status = "pending"  # pending, running, completed, failed
        self.created_at = time.time()
        self.finished_at: Optional[float] = None
        self.steps: List[Dict[str, Any]] = []
        self.result: Optional[Any] = None
        self.error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "status": self.status,
            "created_at": round(self.created_at, 2),
            "finished_at": round(self.finished_at, 2) if self.finished_at else None,
            "step_count": len(self.steps),
            "result": self.result,
            "error": self.error,
        }


class TaskQueue:
    """In-memory async background task manager."""
    def __init__(self):
        self.tasks: Dict[str, TaskRecord] = {}

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        return self.tasks.get(task_id)

    async def submit_task(self, agent: Agent, prompt: str, session_id: str) -> TaskRecord:
        task_id = str(uuid.uuid4())
        record = TaskRecord(
            task_id=task_id,
            agent_name=agent.__class__.__name__,
            session_id=session_id,
            prompt=prompt
        )
        self.tasks[task_id] = record

        # Launch background worker
        asyncio.create_task(self._run_worker(record, agent, prompt, session_id))
        return record

    async def _run_worker(self, record: TaskRecord, agent: Agent, prompt: str, session_id: str):
        record.status = "running"
        try:
            async for step in agent.run(query=prompt, session_id=session_id):
                step_type = step.__class__.__name__
                step_data = step.model_dump() if hasattr(step, "model_dump") else {}
                record.steps.append({"type": step_type, "data": step_data})

                if isinstance(step, FinalResponseStep):
                    text = step.text
                    if hasattr(text, "model_dump"):
                        text = text.model_dump()
                    record.result = text
                elif isinstance(step, ValidationErrorStep):
                    record.error = "; ".join(step.errors)

            record.status = "completed" if not record.error else "failed"
        except Exception as e:
            record.status = "failed"
            record.error = str(e)
        finally:
            record.finished_at = time.time()


# Global task queue singleton
task_queue = TaskQueue()
