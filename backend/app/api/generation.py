from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from app.rendering.base import DocumentExporter

from app.schemas.generation import GeneratedDocument, HandoverGenerationRequest
from app.services.handover_generation_service import HandoverGenerationService

router = APIRouter(prefix='/generation', tags=['generation'])


def get_generation_service(request: Request) -> HandoverGenerationService:
    return request.app.state.handover_generation_service


@router.post('/handover', response_model=GeneratedDocument)
async def generate_handover(body: HandoverGenerationRequest,
                           service: Annotated[HandoverGenerationService, Depends(get_generation_service)]):
    return await service.generate(body)


def get_document_exporter(request: Request) -> DocumentExporter:
    return request.app.state.document_exporter


@router.post('/handover/pdf', response_class=Response,
             responses={200: {'content': {'application/pdf': {}}}})
def download_handover_pdf(body: GeneratedDocument,
                          exporter: Annotated[DocumentExporter, Depends(get_document_exporter)]):
    result = exporter.export(body)
    return Response(result.content, media_type=result.media_type,
                    headers={'Content-Disposition': 'attachment; filename="handover.pdf"',
                             'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
