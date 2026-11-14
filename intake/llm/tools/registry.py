"""Central tool registry and dispatcher for the intake agent."""

from typing import Any, Callable, Dict, List, Tuple
from pydantic import BaseModel, ValidationError

from intake.llm.tools.list_documents import list_documents, ListDocumentsInput
from intake.llm.tools.classify_document import classify_document, ClassifyDocumentInput
from intake.llm.tools.extract_fields import extract_fields, ExtractFieldsInput
from intake.llm.tools.check_completeness import check_completeness, CheckCompletenessInput


TOOL_REGISTRY: Dict[str, Tuple[type[BaseModel], Callable[[Any], BaseModel]]] = {
    "list_documents": (ListDocumentsInput, list_documents),
    "classify_document": (ClassifyDocumentInput, classify_document),
    "extract_fields": (ExtractFieldsInput, extract_fields),
    "check_completeness": (CheckCompletenessInput, check_completeness),
}


def get_available_tools() -> List[str]:
    """Get list of registered tool names."""
    return list(TOOL_REGISTRY.keys())


def execute_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate arguments and execute tool by name, returning a JSON-serializable dict.
    
    Raises:
        KeyError: If tool_name is not registered.
        ValidationError: If tool_args do not conform to schema.
    """
    if tool_name not in TOOL_REGISTRY:
        raise KeyError(f"Unknown tool: '{tool_name}'. Available tools: {get_available_tools()}")
    
    schema_cls, func = TOOL_REGISTRY[tool_name]
    parsed_input = schema_cls.model_validate(tool_args)
    result = func(parsed_input)
    return result.model_dump()
