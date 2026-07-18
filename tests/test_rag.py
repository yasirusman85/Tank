import os
import pytest
from tank import (
    SQLAlchemyMemory,
    TokenBufferMemory,
    SimpleMemory,
    MockEmbeddings,
    SimpleVectorStore,
    Retriever,
    Agent,
    LLM,
)

@pytest.mark.asyncio
async def test_sqlalchemy_memory():
    # Use in-memory SQLite database for testing
    db_url = "sqlite+aiosqlite:///:memory:"
    memory = SQLAlchemyMemory(db_url=db_url)
    
    session_id = "test-session-sqla"
    
    # 1. Retrieve on empty memory
    msgs = await memory.get_messages(session_id)
    assert msgs == []
    
    # 2. Add some messages
    user_msg = {"role": "user", "content": "What is SQLAlchemy?"}
    await memory.add_message(session_id, user_msg)
    
    assistant_msg = {
        "role": "assistant",
        "thought": "SQLAlchemy is an ORM.",
        "content": "SQLAlchemy is a Python SQL toolkit."
    }
    await memory.add_message(session_id, assistant_msg)
    
    # 3. Retrieve and verify
    history = await memory.get_messages(session_id)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "What is SQLAlchemy?"
    assert history[1]["role"] == "assistant"
    assert history[1]["thought"] == "SQLAlchemy is an ORM."
    assert history[1]["content"] == "SQLAlchemy is a Python SQL toolkit."
    
    # 4. Clear and verify
    await memory.clear(session_id)
    cleared = await memory.get_messages(session_id)
    assert cleared == []


@pytest.mark.asyncio
async def test_token_buffer_memory():
    base_mem = SimpleMemory()
    # Limit to about 50 tokens (200 characters)
    memory = TokenBufferMemory(base_mem, max_tokens=50)
    session_id = "token-session"
    
    # System prompt (must always be preserved)
    await memory.add_message(session_id, {"role": "system", "content": "System directive here."})
    
    # Message 1
    await memory.add_message(session_id, {"role": "user", "content": "A very long message " * 10}) # ~180 chars
    # Message 2 (most recent)
    await memory.add_message(session_id, {"role": "assistant", "content": "Short response."}) # ~15 chars
    
    # Retrieval should drop the very long user message, but keep the system directive and the most recent response
    history = await memory.get_messages(session_id)
    
    assert len(history) > 0
    assert history[0]["role"] == "system"
    assert history[-1]["role"] == "assistant"
    assert history[-1]["content"] == "Short response."
    # The middle long message should be dropped because it pushes total count beyond ~50 tokens (including system)
    assert not any(len(msg.get("content", "")) > 100 for msg in history)


@pytest.mark.asyncio
async def test_embeddings_and_vectorstore(tmp_path):
    embeddings = MockEmbeddings(dimension=128)
    
    # Test query embed
    query_vector = await embeddings.embed_query("test query")
    assert len(query_vector) == 128
    
    # Test vector store persistence
    db_file = os.path.join(tmp_path, "vector_store.json")
    store = SimpleVectorStore(embeddings, persist_path=db_file)
    
    texts = [
        "Python is a programming language.",
        "SQLAlchemy is an ORM database framework.",
        "Tank is an AI-native framework."
    ]
    metadatas = [
        {"category": "languages"},
        {"category": "databases"},
        {"category": "frameworks"}
    ]
    
    await store.add_texts(texts, metadatas=metadatas)
    
    # Check similarity search
    results = await store.similarity_search("Tell me about Tank", k=1)
    assert len(results) == 1
    assert "Tank" in results[0]["text"]
    assert results[0]["metadata"]["category"] == "frameworks"
    assert "score" in results[0]
    
    # Verify save works
    assert os.path.exists(db_file)
    
    # Load into a new store instance and search
    new_store = SimpleVectorStore(embeddings, persist_path=db_file)
    new_results = await new_store.similarity_search("Python info", k=1)
    assert len(new_results) == 1
    assert "Python" in new_results[0]["text"]
    assert new_results[0]["metadata"]["category"] == "languages"


@pytest.mark.asyncio
async def test_retriever_tool():
    embeddings = MockEmbeddings(dimension=64)
    store = SimpleVectorStore(embeddings)
    await store.add_texts(["Paris is the capital of France.", "Berlin is the capital of Germany."])
    
    retriever = Retriever(store, k=1)
    retriever_tool = retriever.as_tool(name="kb_search")
    
    assert retriever_tool.name == "kb_search"
    
    # Run the retriever tool
    res = await retriever_tool(query="capital of France")
    assert "capital of France" in res or "Paris" in res
