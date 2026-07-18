import os
import sys
import shutil
import pytest
from unittest.mock import patch
from tank.cli.main import main

def test_cli_startproject(tmp_path):
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    
    try:
        # Mock sys.argv to run: tank startproject my_demo_app
        with patch.object(sys, 'argv', ['tank', 'startproject', 'my_demo_app']):
            main()
            
        # Verify structure
        project_dir = tmp_path / "my_demo_app"
        assert os.path.exists(project_dir)
        assert os.path.exists(project_dir / "app.py")
        assert os.path.exists(project_dir / "settings.py")
        assert os.path.exists(project_dir / ".env")
        assert os.path.exists(project_dir / "agents" / "__init__.py")
        
        # Read files to confirm boilerplate is correct
        with open(project_dir / "settings.py", "r") as f:
            content = f.read()
            assert "DATABASE_URL = " in content
            
        with open(project_dir / "app.py", "r") as f:
            app_content = f.read()
            assert "Tank()" in app_content
            
    finally:
        os.chdir(old_cwd)

def test_cli_startagent(tmp_path):
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    
    try:
        # First test startagent outside project
        with patch.object(sys, 'argv', ['tank', 'startagent', 'hello_bot']):
            main()
            
        assert os.path.exists(tmp_path / "hello_bot.py")
        with open(tmp_path / "hello_bot.py", "r") as f:
            content = f.read()
            assert "class HelloBotAgent(Agent):" in content
            assert "tools = [sample_tool]" in content

        # Now test startagent inside a project folder structure
        os.makedirs(tmp_path / "agents")
        with open(tmp_path / "agents" / "__init__.py", "w") as f:
            f.write("")
            
        with patch.object(sys, 'argv', ['tank', 'startagent', 'math_assistant']):
            main()
            
        assert os.path.exists(tmp_path / "agents" / "math_assistant.py")
        with open(tmp_path / "agents" / "math_assistant.py", "r") as f:
            agent_content = f.read()
            assert "class MathAssistantAgent(Agent):" in agent_content

        with open(tmp_path / "agents" / "__init__.py", "r") as f:
            init_content = f.read()
            assert "from .math_assistant import MathAssistantAgent" in init_content
            
    finally:
        os.chdir(old_cwd)
