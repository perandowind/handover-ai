from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

# The existing Phase 3 structured output contracts are also the API response.
from app.schemas.llm import GeneratedDocument, GeneratedSection  # noqa: F401


class HandoverGenerationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, strict=True)
    prompt: str = Field(min_length=1, max_length=4000)
    document_ids: list[Annotated[int, Field(gt=0, le=2**63-1)]] | None = Field(default=None, max_length=100)

    @field_validator('document_ids')
    @classmethod
    def unique_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError('document_ids must be unique')
        return value or None
