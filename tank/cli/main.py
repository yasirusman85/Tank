import os
import sys
import argparse
import uvicorn

SETTINGS_TEMPLATE = """# Tank settings configuration file.
import os

# Default LLM configurations
DEFAULT_PROVIDER = "mock"
DEFAULT_MODEL = None
MEMORY_BACKEND = "sqlalchemy"
DATABASE_URL = "sqlite+aiosqlite:///tank_memory.db"

# API keys loaded from the environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
"""

APP_TEMPLATE = """import uvicorn
from tank import Tank
# Import your custom agent
# from agents.bot import BotAgent

app = Tank()

@app.route("/")
async def home(request):

    from starlette.responses import JSONResponse
    return JSONResponse({"status": "healthy", "framework": "Tank"})

# @app.agent_route("/chat")
# class MainAgent(BotAgent):
#     pass

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
"""

AGENT_TEMPLATE = """from tank import Agent, LLM, tool

@tool
def sample_tool(query: str) -> str:
    \"\"\"
    A sample tool for the agent.
    
    Args:
        query: The search query argument.
    \"\"\"
    return f"Search result for '{{query}}'"

class {class_name}Agent(Agent):
    \"\"\"
    A custom Agent subclass pre-wired with a mock LLM and a tool.
    \"\"\"
    llm = LLM(provider="mock")
    tools = [sample_tool]
"""

ENV_TEMPLATE = """# Environment Variables for Tank application
OPENAI_API_KEY=your-openai-api-key-here
ANTHROPIC_API_KEY=your-anthropic-api-key-here
"""

# Startup banner
BANNER = """
\033[94m
  _____             _     
 |_   _|_ _ _ __   | | __ 
   | |/ _` | '_ \\  | |/ / 
   | | (_| | | | | |   <  
   |_|\\__,_|_| |_| |_|\\_\\ 
                          
\033[0m\033[92m Tank AI-Native Web Framework \033[0m
"""

def main():
    # Ensure ANSI codes work on Windows terminals if possible
    if sys.platform == "win32":
        os.system("color")

    parser = argparse.ArgumentParser(description="Tank Command Line Utility")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # startproject command
    parser_sp = subparsers.add_parser("startproject", help="Create a new Tank project")
    parser_sp.add_argument("name", help="Name of the project directory")

    # startagent command
    parser_sa = subparsers.add_parser("startagent", help="Create a new Agent template")
    parser_sa.add_argument("name", help="Name of the Agent (e.g. researcher)")

    # runserver command
    parser_rs = subparsers.add_parser("runserver", help="Launch the local development server")
    parser_rs.add_argument("--host", default="127.0.0.1", help="Dev server host bind IP")
    parser_rs.add_argument("--port", type=int, default=8000, help="Dev server port")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "startproject":
        project_dir = args.name
        if os.path.exists(project_dir):
            print(f"\033[91mError: Directory '{project_dir}' already exists.\033[0m")
            sys.exit(1)

        os.makedirs(project_dir)
        os.makedirs(os.path.join(project_dir, "agents"))
        
        # Write app.py
        with open(os.path.join(project_dir, "app.py"), "w", encoding="utf-8") as f:
            f.write(APP_TEMPLATE)
            
        # Write settings.py
        with open(os.path.join(project_dir, "settings.py"), "w", encoding="utf-8") as f:
            f.write(SETTINGS_TEMPLATE)

        # Write .env
        with open(os.path.join(project_dir, ".env"), "w", encoding="utf-8") as f:
            f.write(ENV_TEMPLATE)

        # Write agents/__init__.py
        with open(os.path.join(project_dir, "agents", "__init__.py"), "w", encoding="utf-8") as f:
            f.write("# Sub-package for Tank agents\n")

        print(f"\033[92mProject '{project_dir}' created successfully!\033[0m")
        print(f"Run: cd {project_dir}; tank runserver")

    elif args.command == "startagent":
        agent_name = args.name
        # Convert snake_case or spaces to CamelCase
        words = agent_name.replace("_", " ").split(" ")
        class_name = "".join(w.capitalize() for w in words)
        
        # Determine if we are inside a Tank project folder
        agents_dir = "agents"
        if os.path.exists(agents_dir) and os.path.isdir(agents_dir):
            target_path = os.path.join(agents_dir, f"{agent_name}.py")
        else:
            target_path = f"{agent_name}.py"
            
        if os.path.exists(target_path):
            print(f"\033[91mError: Agent file '{target_path}' already exists.\033[0m")
            sys.exit(1)

        content = AGENT_TEMPLATE.format(class_name=class_name)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        # Append class import to __init__.py if we are inside a project
        init_path = os.path.join(agents_dir, "__init__.py")
        if os.path.exists(init_path):
            with open(init_path, "a", encoding="utf-8") as f:
                f.write(f"from .{agent_name} import {class_name}Agent\n")

        print(f"\033[92mAgent file '{target_path}' generated successfully!\033[0m")

    elif args.command == "runserver":
        print(BANNER)
        print(f"Starting Tank local development server on http://{args.host}:{args.port} ...")
        print("Press CTRL+C to quit.")
        print("-" * 60)
        
        # Check that app.py exists before starting uvicorn
        if not os.path.exists("app.py"):
            print("\033[91mError: 'app.py' not found in current directory. Please run this inside a Tank project folder.\033[0m")
            sys.exit(1)

        try:
            uvicorn.run("app:app", host=args.host, port=args.port, reload=True)
        except KeyboardInterrupt:
            print("\nServer shut down successfully.")
            sys.exit(0)
