import uvicorn
from tank import Tank, Agent, tool, LLM

# Initialize the Tank web application
app = Tank()

@tool
def add(a: int, b: int) -> int:
    """
    Adds two integers.
    """
    return a + b

@app.agent_route("/chat")
class CalculatorAgent(Agent):
    """
    An agent equipped with a calculator tool to perform additions.
    """
    llm = LLM(provider="mock")
    tools = [add]

if __name__ == "__main__":
    print("Starting Tank CalculatorAgent demo server on http://127.0.0.1:8000...")
    uvicorn.run("example.app:app", host="127.0.0.1", port=8000, log_level="info")
