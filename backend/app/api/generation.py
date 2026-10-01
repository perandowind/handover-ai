from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.schemas.generation import GeneratedDocument, HandoverGenerationRequest
from app.services.handover_generation_service import HandoverGenerationService

router = APIRouter(prefix='/generation', tags=['generation'])


def get_generation_service(request: Request) -> HandoverGenerationService:
    return request.app.state.handover_generation_service


@router.post('/handover', response_model=GeneratedDocument)
async def generate_handover(body: HandoverGenerationRequest,
                           service: Annotated[HandoverGenerationService, Depends(get_generation_service)]):
    return await service.generate(body)
