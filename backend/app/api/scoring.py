from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.schemas.scoring import ScoringRequest, ScoringResult
from app.services.scoring_service import ScoringService

router = APIRouter(prefix='/scoring', tags=['scoring'])


def get_scoring_service(request: Request) -> ScoringService:
    return request.app.state.scoring_service


@router.post('/evaluate', response_model=ScoringResult)
async def evaluate(body: ScoringRequest, service: Annotated[ScoringService, Depends(get_scoring_service)]):
    return await service.evaluate(body)
