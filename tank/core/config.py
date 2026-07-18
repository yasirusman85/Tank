"""
Configuration and settings singleton manager for Tank framework.
Loads settings from environment variables and overrides from local settings.py.
"""
import os
import sys
import logging
import importlib.util

logger = logging.getLogger("tank.config")

class Settings:
    """
    Global settings manager for Tank.
    Loads defaults from environment variables, and overrides them with variables
    defined in a local 'settings.py' file in the current working directory.
    """
    def __init__(self):
        # Set default values
        self.DEFAULT_PROVIDER = os.getenv("TANK_DEFAULT_PROVIDER", "mock")
        self.DEFAULT_MODEL = os.getenv("TANK_DEFAULT_MODEL", None)
        self.DATABASE_URL = os.getenv("TANK_DATABASE_URL", "sqlite+aiosqlite:///tank_memory.db")
        self.MEMORY_BACKEND = os.getenv("TANK_MEMORY_BACKEND", "simple")

        
        # API Keys
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", None)
        self.ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", None)
        
        # Load local settings.py if present
        self._load_local_settings()

    def _load_local_settings(self):
        cwd = os.getcwd()
        settings_path = os.path.join(cwd, "settings.py")
        if os.path.exists(settings_path):
            try:
                # Add CWD to system path temporarily to support imports
                if cwd not in sys.path:
                    sys.path.insert(0, cwd)
                
                spec = importlib.util.spec_from_file_location("local_settings", settings_path)
                if spec and spec.loader:
                    local_settings = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(local_settings)
                    
                    # Overlay all UPPERCASE attributes
                    for key in dir(local_settings):
                        if key.isupper():
                            setattr(self, key, getattr(local_settings, key))
            except Exception as e:
                logger.warning(f"Could not load local settings from {settings_path}: {e}")


# Global singleton settings object
settings = Settings()
