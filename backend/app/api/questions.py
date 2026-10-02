from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.repositories.question_repository import QuestionRepository
from app.schemas.question import QuestionAnswer, QuestionGenerationRequest, QuestionRead
from app.services.question_service import QuestionService

router = APIRouter(prefix='/questions', tags=['questions'])


def get_question_repository(request: Request) -> QuestionRepository:
    return request.app.state.question_repository


def get_question_service(request: Request) -> QuestionService:
    return request.app.state.question_service


@router.post('/generate', response_model=list[QuestionRead], status_code=201)
async def generate(body: QuestionGenerationRequest, service: Annotated[QuestionService, Depends(get_question_service)]):
    return await service.generate(body)


@router.get('', response_model=list[QuestionRead])
def list_questions(repository: Annotated[QuestionRepository, Depends(get_question_repository)],
                   offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    return repository.list(offset, limit)


@router.get('/{question_id}', response_model=QuestionRead)
def question(question_id: int, repository: Annotated[QuestionRepository, Depends(get_question_repository)]):
    return repository.get(question_id)


@router.get('/{question_id}/answer', response_model=QuestionAnswer)
def answer(question_id: int, repository: Annotated[QuestionRepository, Depends(get_question_repository)]):
    return repository.get(question_id)
