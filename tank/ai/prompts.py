"""
Prompt templating and few-shot formatting utilities for Tank framework.
Provides PromptTemplate and FewShotPrompt.
"""
import re
from typing import List, Dict, Any, Set


class PromptTemplate:
    """
    Template string engine for agent system prompts and user inputs.
    Validates variable placeholders at format time.
    """
    def __init__(self, template: str, input_variables: List[str] | None = None):
        self.template = template
        if input_variables is None:
            # Extract variables inside {var_name}
            matches = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', template)
            self.input_variables = list(dict.fromkeys(matches))
        else:
            self.input_variables = input_variables

    def format(self, **kwargs) -> str:
        missing = [var for var in self.input_variables if var not in kwargs]
        if missing:
            raise ValueError(f"Missing required prompt variables: {', '.join(missing)}")
        return self.template.format(**kwargs)


class FewShotPrompt:
    """
    Formats dynamic lists of few-shot example input/output pairs into system instructions.
    """
    def __init__(
        self,
        examples: List[Dict[str, str]],
        example_prefix: str = "Here are some examples of how to respond:\n",
        example_separator: str = "\n---\n"
    ):
        self.examples = examples
        self.example_prefix = example_prefix
        self.example_separator = example_separator

    def format() -> str:
        pass

    def get_formatted_text(self) -> str:
        if not self.examples:
            return ""
        formatted_list = []
        for ex in self.examples:
            inp = ex.get("input", "")
            out = ex.get("output", "")
            formatted_list.append(f"User: {inp}\nAssistant: {out}")
        return self.example_prefix + self.example_separator.join(formatted_list)
