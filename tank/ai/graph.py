"""
State graph workflow engine and GraphAgent for Tank framework.
Enables LangGraph-style directed acyclic (DAG) and cyclic state machine execution workflows.
"""
from typing import Dict, Any, List, Callable, Optional, AsyncGenerator
from tank.ai.agents import Agent, AgentStep, ThoughtStep, FinalResponseStep


class StateGraph:
    """
    Defines a state machine workflow containing nodes (functions/Agents) and edges.
    """
    def __init__(self):
        self.nodes: Dict[str, Any] = {}
        self.edges: Dict[str, str] = {}
        self.conditional_edges: Dict[str, Callable[[Dict[str, Any]], str]] = {}
        self.entry_point: Optional[str] = None

    def add_node(self, name: str, action: Any):
        """Register a processing node (callable or Agent instance)."""
        self.nodes[name] = action

    def set_entry_point(self, name: str):
        """Set the starting node of the graph execution."""
        self.entry_point = name

    def add_edge(self, start_node: str, end_node: str):
        """Add a static directed edge from start_node to end_node."""
        self.edges[start_node] = end_node

    def add_conditional_edges(self, start_node: str, routing_func: Callable[[Dict[str, Any]], str]):
        """Add a dynamic edge routed by evaluating routing_func(state)."""
        self.conditional_edges[start_node] = routing_func

    def compile(self) -> "GraphAgent":
        """Compiles graph into an executable GraphAgent instance."""
        return GraphAgent(graph=self)


class GraphAgent(Agent):
    """
    Agent subclass executing a compiled StateGraph workflow.
    """
    def __init__(self, graph: StateGraph, **kwargs):
        super().__init__(**kwargs)
        self.graph = graph

    async def run(self, query: str, session_id: str = "default") -> AsyncGenerator[AgentStep, None]:
        if not self.graph.entry_point or self.graph.entry_point not in self.graph.nodes:
            yield ThoughtStep(thought="Graph entry point invalid or missing.")
            yield FinalResponseStep(text="Invalid graph configuration.")
            return

        state: Dict[str, Any] = {"query": query, "session_id": session_id, "history": []}
        current_node_name = self.graph.entry_point

        visited = 0
        max_graph_steps = 10

        while current_node_name and visited < max_graph_steps:
            visited += 1
            yield ThoughtStep(thought=f"[Graph Node: {current_node_name}] Executing step {visited}")
            
            node_action = self.graph.nodes[current_node_name]

            # Execute node action
            if isinstance(node_action, Agent):
                async for step in node_action.run(state["query"], session_id=session_id):
                    yield step
                    if isinstance(step, FinalResponseStep):
                        state["query"] = str(step.text)
            elif callable(node_action):
                res = node_action(state)
                if asyncio.iscoroutine(res):
                    res = await res
                if isinstance(res, dict):
                    state.update(res)
                elif res:
                    state["query"] = str(res)

            state["history"].append(current_node_name)

            # Determine next node transition
            if current_node_name in self.graph.conditional_edges:
                routing_func = self.graph.conditional_edges[current_node_name]
                current_node_name = routing_func(state)
            elif current_node_name in self.graph.edges:
                current_node_name = self.graph.edges[current_node_name]
            else:
                break

        yield FinalResponseStep(text=state.get("query", "Graph execution completed."))


import asyncio
