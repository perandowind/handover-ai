from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import Document, DocumentPage, DocumentSection, HandoverItem


class DocumentRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, document_id: int) -> Document:
        document = self.session.get(Document, document_id)
        if document is None:
            raise AppError('DOCUMENT_NOT_FOUND', '문서를 찾을 수 없습니다.', 404)
        return document

    def list(self, offset: int, limit: int):
        return self.session.scalars(select(Document).order_by(Document.id.desc()).offset(offset).limit(limit)).all()

    def pages(self, document_id: int):
        return self.session.scalars(select(DocumentPage).where(DocumentPage.document_id == document_id)
                                    .order_by(DocumentPage.page_number)).all()

    def sections(self, document_id: int):
        return self.session.scalars(select(DocumentSection).where(DocumentSection.document_id == document_id)
                                    .order_by(DocumentSection.sequence)).all()

    def items(self, document_id: int):
        return self.session.scalars(select(HandoverItem).where(HandoverItem.document_id == document_id)
                                    .order_by(HandoverItem.id)).all()
