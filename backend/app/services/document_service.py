import json
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError
from app.models import Document
from app.ocr.pdf_renderer import PdfRenderer

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(self, settings: Settings, renderer: PdfRenderer):
        self.settings, self.renderer = settings, renderer

    def upload(self, file: UploadFile, session: Session) -> Document:
        name = (file.filename or '').replace('\\', '/').rsplit('/', 1)[-1]
        if not name.lower().endswith('.pdf') or file.content_type not in {'application/pdf', 'application/octet-stream'}:
            raise AppError('INVALID_PDF', 'PDF 파일만 업로드할 수 있습니다.', 415)
        target = self.settings.upload_dir / f'{uuid4().hex}.pdf'
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            total = 0
            with target.open('xb') as output:
                while chunk := file.file.read(1024 * 1024):
                    total += len(chunk)
                    if total > self.settings.max_upload_bytes:
                        raise AppError('UPLOAD_TOO_LARGE', '업로드 크기 제한을 초과했습니다.', 413)
                    output.write(chunk)
            self.renderer.validate(target)
            document = Document(title=Path(name).stem, document_type='handover',
                                source_filename=name, source_path=str(target), ocr_status='pending')
            session.add(document)
            session.commit()
            session.refresh(document)
            logger.info('PDF upload document_id=%s bytes=%s', document.id, total)
            return document
        except Exception:
            session.rollback()
            target.unlink(missing_ok=True)
            raise
        finally:
            file.file.close()


def read_processing_error(settings: Settings, document_id: int):
    path = settings.ocr_result_dir / str(document_id) / 'error.json'
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    return None
