import pytest
from pydantic import Field, ValidationError
from tank.ai.tools import tool, Tool

@pytest.mark.asyncio
async def test_sync_tool_creation():
    @tool
    def add(a: int, b: int = 10) -> int:
        """Add two numbers."""
        return a + b

    assert isinstance(add, Tool)
    assert add.name == "add"
    assert add.description == "Add two numbers."
    
    # Test execution
    res = await add(a=5, b=5)
    assert res == 10

    
@pytest.mark.asyncio
async def test_tool_calling():
    @tool
    def add(a: int, b: int = 10) -> int:
        """Add two numbers."""
        return a + b

    @tool
    async def async_multiply(x: float, y: float) -> float:
        """Multiply two floats."""
        return x * y

    # Test sync execution wrapper
    res_sync = await add(a=5, b=15)
    assert res_sync == 20

    # Test default value
    res_default = await add(a=5)
    assert res_default == 15

    # Test async execution wrapper
    res_async = await async_multiply(x=2.5, y=4.0)
    assert res_async == 10.0

@pytest.mark.asyncio
async def test_tool_schema_generation():
    @tool(name="custom_search", description="Search the web database.")
    def search(query: str, limit: int = 5) -> str:
        return "results"

    schema_openai = search.to_json_schema(provider="openai")
    assert schema_openai["type"] == "function"
    assert schema_openai["function"]["name"] == "custom_search"
    assert schema_openai["function"]["description"] == "Search the web database."
    assert "query" in schema_openai["function"]["parameters"]["properties"]
    assert "limit" in schema_openai["function"]["parameters"]["properties"]
    assert schema_openai["function"]["parameters"]["required"] == ["query"]

    schema_anthropic = search.to_json_schema(provider="anthropic")
    assert schema_anthropic["name"] == "custom_search"
    assert schema_anthropic["description"] == "Search the web database."
    assert "input_schema" in schema_anthropic
    assert "query" in schema_anthropic["input_schema"]["properties"]

@pytest.mark.asyncio
async def test_tool_argument_validation():
    @tool
    def strict_add(a: int, b: int) -> int:
        return a + b

    # Test validation error
    with pytest.raises(ValidationError):
        # Passing string 'hello' instead of int
        await strict_add(a="hello", b=10)
