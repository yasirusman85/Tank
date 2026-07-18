import inspect
from typing import Callable, Any, get_type_hints, Dict, Type
from pydantic import create_model, BaseModel, Field

def parse_docstring_params(doc: str) -> dict[str, str]:
    """
    Parses parameter descriptions from function docstrings.
    Supports both Google-style (Args:) and Sphinx-style (:param name:).
    """
    if not doc:
        return {}
    params = {}
    lines = doc.splitlines()
    
    google_mode = False
    
    for line in lines:
        stripped = line.strip()
        
        # Check for Google style start
        if stripped.lower() in ("args:", "arguments:", "parameters:"):
            google_mode = True
            continue
        # Stop Google mode if we hit another section header in Google style (e.g. Returns:)
        elif google_mode and stripped.endswith(":") and not stripped.startswith("-"):
            if stripped.lower() in ("returns:", "yields:", "raises:", "examples:", "note:", "notes:"):
                google_mode = False
                
        if google_mode:
            # Matches: name (type): description OR name: description
            import re
            m = re.match(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\([^)]+\))?\s*:\s*(.*)$", line)
            if m:
                pname = m.group(1)
                pdesc = m.group(2).strip()
                params[pname] = pdesc
        else:
            # Sphinx style: :param name: description
            import re
            m = re.match(r"^\s*:(?:param|parameter)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.*)$", line)
            if m:
                pname = m.group(1)
                pdesc = m.group(2).strip()
                params[pname] = pdesc
                
    return params

class Tool:
    def __init__(
        self,
        func: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
        requires_approval: bool = False
    ):
        self.func = func
        self.name = name or func.__name__
        self.description = description or func.__doc__ or ""
        self.requires_approval = requires_approval

        
        # Parse parameter descriptions from the docstring
        param_descriptions = parse_docstring_params(self.description)
        
        # Analyze parameters and create a dynamic Pydantic model for validation
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)
        
        fields: Dict[str, Any] = {}
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            
            param_type = type_hints.get(param_name, Any)
            pdesc = param_descriptions.get(param_name, "")
            
            # Check if there is a default value
            if param.default is inspect.Parameter.empty:
                if pdesc:
                    fields[param_name] = (param_type, Field(default=..., description=pdesc))
                else:
                    fields[param_name] = (param_type, ...)
            else:
                if pdesc:
                    fields[param_name] = (param_type, Field(default=param.default, description=pdesc))
                else:
                    fields[param_name] = (param_type, param.default)
                
        self.args_model: Type[BaseModel] = create_model(
            f"{self.name}_args",
            **fields
        )

    def to_json_schema(self, provider: str = "openai") -> dict:
        """
        Generate tool/function schema format for the specified provider ('openai' or 'anthropic').
        """
        schema = self.args_model.model_json_schema()
        # Clean up unwanted keys from Pydantic schema
        schema.pop("title", None)
        
        # Recursively remove titles from properties to clean up the schema for LLMs
        if "properties" in schema:
            for prop in schema["properties"].values():
                if isinstance(prop, dict):
                    prop.pop("title", None)

        if provider == "anthropic":
            return {
                "name": self.name,
                "description": self.description.strip(),
                "input_schema": schema
            }
        else:
            # Default to OpenAI format
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description.strip(),
                    "parameters": schema
                }
            }
        
    async def __call__(self, *args, **kwargs) -> Any:
        # Support positional args by binding them first
        sig = inspect.signature(self.func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        
        # Validate arguments using Pydantic model
        validated = self.args_model(**bound.arguments)
        
        # Call the underlying function
        if inspect.iscoroutinefunction(self.func):
            return await self.func(**validated.model_dump())
        else:
            return self.func(**validated.model_dump())

def tool(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    requires_approval: bool = False
):
    """
    Decorator to register a function as a Tank tool.
    Can be used as @tool or @tool(name="custom_name", description="custom_desc")
    """
    def decorator(f: Callable[..., Any]) -> Tool:
        return Tool(f, name=name, description=description, requires_approval=requires_approval)
        
    if func is None:
        return decorator
    return decorator(func)

