import uuid
import asyncio
import inspect
from typing import Dict, Any, List, Optional, Callable
from pydantic import BaseModel, Field

class ToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: List[ToolParameter]
    category: str  # "tabular", "retrieval", "sandbox", "multimodal"
    timeout_seconds: int = 30
    input_model: Optional[Any] = None
    max_attempts: int = 1
    retryable_errors: List[str] = Field(default_factory=list)
    safety_classification: str = "read_only"
    side_effect_classification: str = "none"
    available: bool = True
    version: str = "1"

class ToolExecutionResult(BaseModel):
    tool_name: str
    success: bool
    data: Any = None
    error_message: Optional[str] = None
    duration_ms: int = 0
    reproducibility_hash: Optional[str] = None

class ToolRegistry:
    """Central registry of type-safe execution tools for the OmniOps agent."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._handlers: Dict[str, Callable] = {}

    def register(self, definition: ToolDefinition, handler: Callable):
        if definition.name in self._tools:
            raise ValueError(f"TOOL_ALREADY_REGISTERED:{definition.name}")
        self._tools[definition.name] = definition
        self._handlers[definition.name] = handler

    def get_definitions(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    async def execute(self, tool_name: str, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolExecutionResult:
        if tool_name not in self._handlers:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error_message=f"Tool '{tool_name}' is not registered in the system."
            )
        
        handler = self._handlers[tool_name]
        definition = self._tools[tool_name]
        if not definition.available:
            return ToolExecutionResult(tool_name=tool_name, success=False, error_message="TOOL_UNAVAILABLE")
        try:
            if definition.input_model is not None:
                validated = definition.input_model.model_validate(arguments)
                arguments = validated.model_dump()
            result = handler(arguments, context)
            if inspect.isawaitable(result):
                result = await asyncio.wait_for(result, timeout=definition.timeout_seconds)
            return result
        except asyncio.TimeoutError:
            return ToolExecutionResult(tool_name=tool_name, success=False, error_message="TOOL_TIMEOUT")
        except Exception as e:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error_message=f"Handler execution error: {str(e)}"
            )

# Global Tool Registry
global_tool_registry = ToolRegistry()
