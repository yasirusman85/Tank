"""
Multi-agent orchestration and SupervisorAgent implementation for Tank framework.
Enables routing queries and delegating execution steps across specialized worker Agents.
"""
from typing import Dict, AsyncGenerator
from tank.ai.agents import Agent, AgentStep, ThoughtStep, HandoffStep


class SupervisorAgent(Agent):
    """
    Orchestrates multiple worker Agents by analyzing incoming queries,
    emitting HandoffSteps, and delegating execution to the selected specialist.
    """
    def __init__(self, workers: Dict[str, Agent], **kwargs):
        super().__init__(**kwargs)
        self.workers = workers

    async def run(self, query: str, session_id: str = "default") -> AsyncGenerator[AgentStep, None]:
        if not self.workers:
            yield ThoughtStep(thought="No worker agents registered. Executing with default supervisor.")
            async for step in super().run(query, session_id=session_id):
                yield step
            return

        # Simple keyword/name routing heuristic (or prompt matching)
        query_lower = query.lower()
        selected_name = list(self.workers.keys())[0]  # Default to first worker
        selected_reason = f"Routing query to primary specialist '{selected_name}'."

        for worker_name in self.workers:
            if worker_name.lower() in query_lower:
                selected_name = worker_name
                selected_reason = f"Explicit match for worker '{worker_name}'."
                break

        target_agent = self.workers[selected_name]

        # Yield HandoffStep
        yield ThoughtStep(thought=f"Supervisor selected worker: {selected_name}")
        yield HandoffStep(
            target_agent=selected_name,
            reason=selected_reason,
            session_id=session_id
        )

        # Delegate execution stream to selected worker agent
        async for step in target_agent.run(query, session_id=session_id):
            yield step
