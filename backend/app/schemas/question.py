from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.generation import HandoverGenerationRequest


class QuestionGenerationRequest(HandoverGenerationRequest):
    prompt: str = Field(default='저장된 문서의 주요 업무에 관한 문제를 만들어줘.', min_length=1, max_length=4000)
    question_type: Literal['multiple_choice', 'short_answer'] = 'multiple_choice'
    count: int = Field(default=5, ge=1, le=20)


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    document_id: int | None
    section_id: int | None
    question_type: Literal['multiple_choice', 'short_answer']
    question_text: str
    choices: list[str] | None
    created_at: datetime


class QuestionAnswer(BaseModel):
    correct_answer: str
    explanation: str | None


class QuestionData(QuestionRead, QuestionAnswer):
    """Internal record; list/quiz endpoints expose only QuestionRead."""
