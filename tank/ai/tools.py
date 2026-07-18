import inspect
from typing import Callable, Any, get_type_hints, Dict, Type
from pydantic import create_model, BaseModel, Field

class Tool:
    def __init__(self, func: Callable[..., Any], name: str | None = None, description: str | None = None):
        self.func = func
        self.name = name or func.__name__
        self.description = description or func.__doc__ or ""
        
        # Analyze parameters and create a dynamic Pydantic model for validation
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)
        
        fields: Dict[str, Any] = {}
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            
            param_type = type_hints.get(param_name, Any)
            
            # Check if there is a default value
            if param.default is inspect.Parameter.empty:
                fields[param_name] = (param_type, ...)
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
    description: str | None = None
):
    """
    Decorator to register a function as a Tank tool.
    Can be used as @tool or @tool(name="custom_name", description="custom_desc")
    """
    def decorator(f: Callable[..., Any]) -> Tool:
        return Tool(f, name=name, description=description)
        
    if func is None:
        return decorator
    return decorator(func)
