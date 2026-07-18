import json
import datetime
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from sqlalchemy import String, Text, Integer, Column, JSON, DateTime, select, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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


class Base(DeclarativeBase):
    pass

class DBMessage(Base):
    __tablename__ = "tank_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(50))
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thought: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )


class SQLAlchemyMemory(BaseMemory):
    """
    SQLAlchemy-backed message memory store.
    Supports persistent storage (e.g. SQLite, PostgreSQL) using async SQLAlchemy sessions.
    """
    def __init__(self, db_url: str = "sqlite+aiosqlite:///tank_memory.db"):
        self.engine = create_async_engine(db_url)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self._initialized = False

    async def _init_db(self):
        if not self._initialized:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            self._initialized = True

    async def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self.session_factory() as session:
            stmt = select(DBMessage).where(DBMessage.session_id == session_id).order_by(DBMessage.id)
            result = await session.execute(stmt)
            db_msgs = result.scalars().all()
            
            messages = []
            for db_msg in db_msgs:
                msg = {"role": db_msg.role}
                if db_msg.content is not None:
                    msg["content"] = db_msg.content
                if db_msg.thought is not None:
                    msg["thought"] = db_msg.thought
                if db_msg.tool_calls is not None:
                    msg["tool_calls"] = db_msg.tool_calls
                if db_msg.tool_call_id is not None:
                    msg["tool_call_id"] = db_msg.tool_call_id
                if db_msg.name is not None:
                    msg["name"] = db_msg.name
                messages.append(msg)
            return messages

    async def add_message(self, session_id: str, message: Dict[str, Any]) -> None:
        await self._init_db()
        async with self.session_factory() as session:
            db_msg = DBMessage(
                session_id=session_id,
                role=message.get("role"),
                content=message.get("content"),
                thought=message.get("thought"),
                tool_calls=message.get("tool_calls"),
                tool_call_id=message.get("tool_call_id"),
                name=message.get("name")
            )
            session.add(db_msg)
            await session.commit()

    async def clear(self, session_id: str) -> None:
        await self._init_db()
        async with self.session_factory() as session:
            stmt = delete(DBMessage).where(DBMessage.session_id == session_id)
            await session.execute(stmt)
            await session.commit()


class TokenBufferMemory(BaseMemory):
    """
    Memory wrapper that restricts retrieved message history to a maximum token count.
    Saves all messages, but slices retrieval. Always preserves the leading 'system' instruction.
    """
    def __init__(self, target_memory: BaseMemory, max_tokens: int = 2000):
        self.target_memory = target_memory
        self.max_tokens = max_tokens

    def _estimate_tokens(self, message: Dict[str, Any]) -> int:
        # Simple character-based estimation: ~4 chars per token
        text = str(message.get("content") or "") + str(message.get("thought") or "")
        if "tool_calls" in message:
            text += json.dumps(message["tool_calls"])
        if "name" in message:
            text += str(message["name"])
        return max(1, len(text) // 4)

    async def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        messages = await self.target_memory.get_messages(session_id)
        if not messages:
            return []

        # Always preserve the system prompt at index 0 if it exists
        system_msg = None
        start_idx = 0
        if messages[0].get("role") == "system":
            system_msg = messages[0]
            start_idx = 1

        accumulated_tokens = 0
        if system_msg:
            accumulated_tokens += self._estimate_tokens(system_msg)

        keep_messages = []
        # Traverse remaining messages backwards to get the most recent ones first
        for msg in reversed(messages[start_idx:]):
            tokens = self._estimate_tokens(msg)
            if accumulated_tokens + tokens <= self.max_tokens:
                keep_messages.insert(0, msg)
                accumulated_tokens += tokens
            else:
                break

        if system_msg:
            return [system_msg] + keep_messages
        return keep_messages

    async def add_message(self, session_id: str, message: Dict[str, Any]) -> None:
        await self.target_memory.add_message(session_id, message)

    async def clear(self, session_id: str) -> None:
        await self.target_memory.clear(session_id)
