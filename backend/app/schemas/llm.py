"""LLM output contracts from the prototype specification, not API/ORM models.

SQL output validation here is structural ONLY. SQL Validator belongs to Phase 4.
"""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class LLMOutput(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', allow_inf_nan=False)


class SQLGenerationOutput(LLMOutput):
    sql: NonEmptyText
    reason: NonEmptyText


class GeneratedSection(LLMOutput):
    section_type: NonEmptyText
    title: NonEmptyText
    content: NonEmptyText


class GeneratedDocument(LLMOutput):
    title: NonEmptyText
    sections: list[GeneratedSection]


class GeneratedQuestion(LLMOutput):
    question_type: Literal['multiple_choice', 'short_answer']
    question: NonEmptyText
    choices: list[NonEmptyText] | None
    correct_answer: NonEmptyText
    explanation: NonEmptyText
    source_section_id: Annotated[int, Field(gt=0)] | None


class QuestionGenerationResult(LLMOutput):
    questions: list[GeneratedQuestion]


class LLMScoringResult(LLMOutput):
    # Nullable is_correct is still a required key, per the specification.
    score: float = Field(ge=0, le=100)
    is_correct: bool | None
    reason: NonEmptyText
