import json
import logging
from threading import Lock
from pathlib import Path

from sqlalchemy import inspect, or_, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.models import Document, DocumentPage, DocumentSection
from app.ocr.base import OcrEngine
from app.ocr.paddle_ocr import normalize_results
from app.ocr.pdf_renderer import PdfRenderer
from app.ocr.storage import write_json
from app.parsing.reading_order import page_text
from app.parsing.item_mapper import map_handover_items
from app.parsing.section_mapper import SectionParser
from app.repositories.document_repository import DocumentRepository

logger = logging.getLogger(__name__)


class DocumentPipeline:
    def __init__(self, settings: Settings, sessions: sessionmaker, renderer: PdfRenderer,
                 ocr: OcrEngine, parser: SectionParser):
        self.settings, self.sessions, self.renderer = settings, sessions, renderer
        self.ocr, self.parser = ocr, parser
        self._lock = Lock()

    def recover_interrupted(self) -> None:
        # Single-process prototype: a fresh process cannot resume an in-memory task.
        with self.sessions() as session:
            if not inspect(session.get_bind()).has_table('documents'):
                return
            documents = session.scalars(select(Document).where(or_(
                Document.ocr_status.in_(['pending', 'processing']),
                (Document.ocr_status == 'completed') & (Document.parse_status == 'pending'),
            ))).all()
            for doc in documents:
                if doc.ocr_status != 'completed':
                    doc.ocr_status = 'failed'
                doc.parse_status = 'failed'
                self._error(doc.id, 'PROCESSING_INTERRUPTED', '서버가 재시작되어 처리가 중단되었습니다. PDF를 다시 업로드하세요.')
            session.commit()

    def _error(self, document_id: int, code: str, message: str):
        write_json(self.settings.ocr_result_dir / str(document_id) / 'error.json',
                   {'code': code, 'message': message, 'detail': {'document_id': document_id}})

    def run(self, document_id: int) -> None:
        # FastAPI BackgroundTasks uses threads. Serialize model inference and document jobs.
        with self._lock, self.sessions() as session:
            doc = session.get(Document, document_id)
            if doc is None or doc.ocr_status != 'pending':
                return
            stage = 'ocr'
            try:
                doc.ocr_status = 'processing'
                session.commit()
                logger.info('OCR start document_id=%s', document_id)
                count = self.renderer.validate(Path(doc.source_path))
                for number in range(1, count + 1):
                    image_path = self.settings.page_image_dir / str(document_id) / f'page-{number:04}.png'
                    self.renderer.render_page(Path(doc.source_path), number, image_path)
                    page = DocumentPage(document_id=document_id, page_number=number,
                                        image_path=str(image_path), raw_text='', ocr_json='{"status":"pending"}')
                    session.add(page)
                    session.commit()
                    raw = self.ocr.recognize(image_path)
                    payload = {'page_number': number, 'raw_results': raw}
                    raw_path = self.settings.ocr_result_dir / str(document_id) / f'page-{number:04}.json'
                    # Preserve the native result BEFORE validation or parser processing.
                    write_json(raw_path, payload)
                    page.ocr_json = json.dumps(payload, ensure_ascii=False, allow_nan=False)
                    session.commit()
                    lines = normalize_results(raw)
                    payload['lines'] = [line.model_dump() for line in lines]
                    write_json(raw_path, payload)
                    page.raw_text = page_text(lines)
                    page.ocr_json = json.dumps(payload, ensure_ascii=False, allow_nan=False)
                    session.commit()
                    logger.info('OCR page complete document_id=%s page=%s lines=%s', document_id, number, len(lines))
                doc.ocr_status = 'completed'
                session.commit()
                logger.info('OCR end document_id=%s', document_id)
                stage = 'parse'
                logger.info('Document parsing start document_id=%s', document_id)
                pages = DocumentRepository(session).pages(document_id)
                parsed = self.parser.parse([(page.page_number, page.raw_text) for page in pages])
                for section in parsed:
                    record = DocumentSection(document_id=document_id, **vars(section))
                    session.add(record)
                    session.flush()
                    session.add_all(map_handover_items(record))
                doc.parse_status = 'completed'
                session.commit()
                logger.info('Document parsing end document_id=%s sections=%s', document_id, len(parsed))
            except Exception as exc:
                session.rollback()
                logger.error('Document pipeline failure document_id=%s stage=%s error_type=%s',
                             document_id, stage, type(exc).__name__)
                doc = session.get(Document, document_id)
                if doc:
                    if stage == 'ocr':
                        doc.ocr_status = 'failed'
                    doc.parse_status = 'failed'
                    session.commit()
                self._error(document_id, 'OCR_FAILED' if stage == 'ocr' else 'PARSING_FAILED',
                            'OCR 처리에 실패했습니다. OCR 설치·모델·서버 로그를 확인하세요.' if stage == 'ocr'
                            else '문서 구조화에 실패했습니다. OCR 원본은 보존되었습니다.')
