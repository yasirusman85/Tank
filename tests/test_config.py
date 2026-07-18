import os
import sys
import pytest
from tank import settings

def test_default_settings():
    # Verify default values loaded correctly
    assert settings.DEFAULT_PROVIDER == "mock"
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///tank_memory.db"
    assert settings.MEMORY_BACKEND == "simple"

def test_settings_load_from_file(tmp_path):
    # Create a mock settings.py file in the temp path
    settings_file = tmp_path / "settings.py"
    with open(settings_file, "w") as f:
        f.write("DEFAULT_PROVIDER = 'openai'\n")
        f.write("DEFAULT_MODEL = 'gpt-4o'\n")
        f.write("MEMORY_BACKEND = 'sqlalchemy'\n")
        f.write("DATABASE_URL = 'sqlite+aiosqlite:///custom_test_memory.db'\n")
        f.write("CUSTOM_SETTING_VAL = 'tank-cli-test'\n")

    # Change working directory dynamically to trigger loading
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    
    try:
        # Re-instantiate Settings to load from the new local settings file
        from tank.core.config import Settings
        custom_settings = Settings()
        
        assert custom_settings.DEFAULT_PROVIDER == "openai"
        assert custom_settings.DEFAULT_MODEL == "gpt-4o"
        assert custom_settings.MEMORY_BACKEND == "sqlalchemy"
        assert custom_settings.DATABASE_URL == "sqlite+aiosqlite:///custom_test_memory.db"
        assert getattr(custom_settings, "CUSTOM_SETTING_VAL") == "tank-cli-test"
    finally:
        os.chdir(old_cwd)
