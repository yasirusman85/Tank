from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseMemory(ABC):
    @abstractmethod
    async def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieve conversation history for a given session ID."""
        pass

    @abstractmethod
    async def add_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """Add a single message to the conversation history of a session ID."""
        pass

    @abstractmethod
    async def clear(self, session_id: str) -> None:
        """Clear conversation history for a session ID."""
        pass


class SimpleMemory(BaseMemory):
    """An in-memory store for session message history."""
    def __init__(self):
        self._sessions: Dict[str, List[Dict[str, Any]]] = {}

    async def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        return self._sessions.get(session_id, []).copy()

    async def add_message(self, session_id: str, message: Dict[str, Any]) -> None:
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        self._sessions[session_id].append(message)

    async def clear(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id].clear()
