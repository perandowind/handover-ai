from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.schemas.retrieval import RetrievalRequest, RetrievalResponse
from app.services.retrieval_service import RetrievalService

router = APIRouter(prefix='/retrieval', tags=['retrieval'])


def get_retrieval_service(request: Request) -> RetrievalService:
    return request.app.state.retrieval_service


@router.post('/search', response_model=RetrievalResponse)
async def search(body: RetrievalRequest,
                 service: Annotated[RetrievalService, Depends(get_retrieval_service)]):
    return await service.search(body.query)
