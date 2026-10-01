from dataclasses import dataclass
from typing import Generic, Literal

from app.llm.validation import OutputT


@dataclass(frozen=True)
class TaskDefinition(Generic[OutputT]):
    """Configuration contract only. No schema retrieval, SQL execution, or scoring."""
    name: str
    model: str
    system_prompt: str
    response_schema: type[OutputT]
    validation_retries: Literal[0, 1] = 0

    def __post_init__(self):
        if not self.name.strip() or not self.model.strip():
            raise ValueError('Task name and model must not be empty')
        if self.validation_retries not in (0, 1):
            raise ValueError('At most one validation retry is allowed')
