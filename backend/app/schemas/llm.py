"""LLM output contracts from the prototype specification, not API/ORM models.

SQL output validation here is structural ONLY. SQL Validator belongs to Phase 4.
"""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.handover import HANDOVER_OUTLINE

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class LLMOutput(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', allow_inf_nan=False)


class SQLGenerationOutput(LLMOutput):
    sql: NonEmptyText
    reason: NonEmptyText


class GeneratedSection(LLMOutput):
    section_type: Literal['overview', 'responsibilities', 'systems', 'procedures',
                          'precautions', 'troubleshooting', 'contacts', 'references']
    title: NonEmptyText = Field(max_length=100)
    content: NonEmptyText = Field(max_length=12000)

    @model_validator(mode='after')
    def match_section_title(self):
        if self.title != dict(HANDOVER_OUTLINE)[self.section_type]:
            raise ValueError('Section title must match the default outline')
        return self


class GeneratedDocument(LLMOutput):
    title: NonEmptyText = Field(max_length=200)
    sections: list[GeneratedSection] = Field(min_length=8, max_length=8)

    @model_validator(mode='after')
    def match_outline(self):
        if tuple(section.section_type for section in self.sections) != tuple(key for key, _ in HANDOVER_OUTLINE):
            raise ValueError('Include all eight sections once, in the default order')
        return self


class GeneratedQuestion(LLMOutput):
    question_type: Literal['multiple_choice', 'short_answer']
    question: NonEmptyText = Field(max_length=4000)
    choices: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]] | None
    correct_answer: NonEmptyText = Field(max_length=4000)
    explanation: NonEmptyText = Field(max_length=8000)
    source_section_id: Annotated[int, Field(gt=0)] | None


    @model_validator(mode='after')
    def validate_answer(self):
        if self.question_type == 'multiple_choice':
            if self.choices is None or not 2 <= len(self.choices) <= 6:
                raise ValueError('Multiple choice requires 2 to 6 choices')
            normalized = [' '.join(choice.split()).casefold() for choice in self.choices]
            if len(set(normalized)) != len(normalized):
                raise ValueError('Choices must be distinct')
            if self.correct_answer not in {str(index) for index in range(1, len(self.choices) + 1)}:
                raise ValueError('Correct answer must be a one-based choice number')
        elif self.choices is not None:
            raise ValueError('Short answer choices must be null')
        return self


class QuestionGenerationResult(LLMOutput):
    questions: list[GeneratedQuestion] = Field(min_length=1, max_length=20)


class LLMScoringResult(LLMOutput):
    # Nullable is_correct is still a required key, per the specification.
    score: float = Field(ge=0, le=100)
    is_correct: bool | None
    reason: NonEmptyText
