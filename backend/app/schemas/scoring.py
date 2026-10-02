from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.llm import LLMScoringResult


class ScoringRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    question_id: int = Field(gt=0, le=2**63-1)
    answer: str = Field(min_length=1, max_length=4000)

    @field_validator('answer')
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Answer must not be blank')
        return value


class ScoringResult(LLMScoringResult):
    id: int
    question_id: int
    scoring_method: Literal['llm', 'python_fallback']
