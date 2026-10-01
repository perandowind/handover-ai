from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentDetail, DocumentSectionRead, DocumentSummary, UploadResponse
from app.services.document_service import read_processing_error

router = APIRouter(prefix='/documents', tags=['documents'])
SessionDep = Annotated[Session, Depends(get_session)]


@router.post('/upload', status_code=202, response_model=UploadResponse)
def upload_document(request: Request, background_tasks: BackgroundTasks,
                    session: SessionDep, file: Annotated[UploadFile, File()]):
    document = request.app.state.document_service.upload(file, session)
    background_tasks.add_task(request.app.state.document_pipeline.run, document.id)
    return UploadResponse(document_id=document.id)


@router.get('', response_model=list[DocumentSummary])
def list_documents(session: SessionDep, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100)):
    return DocumentRepository(session).list(offset, limit)


@router.get('/{document_id}', response_model=DocumentDetail)
def document_detail(document_id: int, request: Request, session: SessionDep):
    repository = DocumentRepository(session)
    document = repository.get(document_id)
    return {
        **DocumentSummary.model_validate(document).model_dump(),
        'pages': repository.pages(document_id),
        'sections': repository.sections(document_id),
        'handover_items': repository.items(document_id),
        'processing_error': read_processing_error(request.app.state.settings, document_id),
    }


@router.get('/{document_id}/sections', response_model=list[DocumentSectionRead])
def document_sections(document_id: int, session: SessionDep):
    repository = DocumentRepository(session)
    repository.get(document_id)
    return repository.sections(document_id)
