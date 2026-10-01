import json
from pathlib import Path

import pymupdf
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, Settings, get_settings
from app.db.session import create_db_engine
from app.main import create_app
from app.models import Document

SAMPLE = BACKEND_DIR.parent / 'sample-data/scanned-pdfs/db-handover-scan.pdf'


class FakeOcr:
    def __init__(self, fail_page=None, malformed=False, blank=False):
        self.calls = 0
        self.fail_page, self.malformed, self.blank = fail_page, malformed, blank

    def recognize(self, path):
        assert path.is_file()
        self.calls += 1
        if self.calls == self.fail_page:
            raise RuntimeError('private internal error')
        lines = ['1. 업무 개요', '백업 업무', '2. 주요 업무', '업무명: 백업 확인', '설명: 매일 로그 확인'] if self.calls == 1 else ['3. 주의사항', '백업 삭제 금지']
        if self.blank:
            lines = []
        return [{'res': {'rec_texts': lines, 'rec_scores': [.98] * len(lines),
                         'rec_polys': [] if self.malformed else [[[1, i*30], [200, i*30], [200, i*30+20], [1, i*30+20]] for i in range(len(lines))],
                         'native_extra': {'confidence_source': 'recognizer'}}}]


@pytest.fixture
def pipeline_factory(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "pipeline.db"}'
    monkeypatch.setenv('DATABASE_URL', url)
    get_settings.cache_clear()
    command.upgrade(Config(str(BACKEND_DIR / 'alembic.ini')), 'head')
    def factory(ocr=None, parser=None, **overrides):
        settings = Settings(_env_file=None, database_url=url, upload_dir=tmp_path/'uploads',
                            page_image_dir=tmp_path/'pages', ocr_result_dir=tmp_path/'ocr', **overrides)
        return create_app(settings, ocr_engine=ocr or FakeOcr(), section_parser=parser), settings
    yield factory
    get_settings.cache_clear()


def upload(client, content=None, name='scan.pdf', mime='application/pdf'):
    return client.post('/api/documents/upload', files={'file': (name, SAMPLE.read_bytes() if content is None else content, mime)})


def test_image_pdf_to_db_and_api(pipeline_factory):
    app, settings = pipeline_factory()
    with pymupdf.open(SAMPLE) as pdf:
        assert len(pdf) == 2
        assert all(not page.get_text().strip() and page.get_images() for page in pdf)
    with TestClient(app) as client:
        response = upload(client, name='../../scan.pdf')
        assert response.status_code == 202
        assert response.json() == {'document_id': 1, 'status': 'processing'}
        doc = client.get('/api/documents/1').json()
        assert doc['ocr_status'] == doc['parse_status'] == 'completed'
        assert doc['source_filename'] == 'scan.pdf'
        assert len(doc['pages']) == 2 and len(doc['handover_items']) == 3
        assert [s['section_type'] for s in doc['sections']] == ['overview', 'responsibilities', 'precautions']
        assert doc['sections'] == client.get('/api/documents/1/sections').json()
        assert client.get('/api/documents').json()[0]['id'] == 1
        assert client.get('/api/documents?offset=1').json() == []
        assert client.get('/api/documents?limit=101').status_code == 422
        assert len(list(settings.upload_dir.glob('*.pdf'))) == 1
        for page in doc['pages']:
            number = page['page_number']
            saved = json.loads((settings.ocr_result_dir/'1'/f'page-{number:04}.json').read_text())
            assert saved == page['ocr_json']
            assert saved['raw_results'][0]['res']['native_extra']
            assert saved['lines'][0]['confidence'] == .98
            assert len(saved['lines'][0]['bbox']) == 4
            image = pymupdf.Pixmap(settings.page_image_dir/'1'/f'page-{number:04}.png')
            assert image.width > 1600 and image.height > 2300


@pytest.mark.parametrize('path', ['/api/documents/999', '/api/documents/999/sections'])
def test_missing_document(pipeline_factory, path):
    app, _ = pipeline_factory()
    with TestClient(app) as client:
        response = client.get(path)
        assert response.status_code == 404 and response.json()['code'] == 'DOCUMENT_NOT_FOUND'


@pytest.mark.parametrize('content,name,mime,status', [
    (b'not PDF', 'bad.pdf', 'application/pdf', 422),
    (b'%PDF-1.7\ninvalid', 'bad.pdf', 'application/pdf', 422),
    (b'', 'empty.pdf', 'application/pdf', 422),
    (b'anything', 'bad.txt', 'application/pdf', 415),
    (b'anything', 'bad.pdf', 'text/plain', 415),
])
def test_invalid_upload_does_not_create_document(pipeline_factory, content, name, mime, status):
    app, settings = pipeline_factory()
    with TestClient(app) as client:
        response = upload(client, content, name, mime)
        assert response.status_code == status
        assert client.get('/api/documents').json() == []
        assert not settings.upload_dir.exists() or not list(settings.upload_dir.iterdir())


@pytest.mark.parametrize('options,code,status', [
    ({'max_upload_bytes': 10}, 'UPLOAD_TOO_LARGE', 413),
    ({'max_pdf_pages': 1}, 'PDF_PAGE_LIMIT', 422),
    ({'max_page_pixels': 100}, 'PDF_PAGE_TOO_LARGE', 422),
])
def test_upload_limits(pipeline_factory, options, code, status):
    app, _ = pipeline_factory(**options)
    with TestClient(app) as client:
        response = upload(client)
        assert response.status_code == status and response.json()['code'] == code


def test_encrypted_pdf(pipeline_factory):
    with pymupdf.open(SAMPLE) as pdf:
        encrypted = pdf.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='secret')
    app, _ = pipeline_factory()
    with TestClient(app) as client:
        response = upload(client, encrypted)
        assert response.status_code == 422 and response.json()['code'] == 'ENCRYPTED_PDF'


def test_partial_ocr_failure_keeps_first_page_and_original(pipeline_factory):
    app, settings = pipeline_factory(FakeOcr(fail_page=2))
    with TestClient(app) as client:
        assert upload(client).status_code == 202
        doc = client.get('/api/documents/1').json()
        assert doc['ocr_status'] == doc['parse_status'] == 'failed'
        assert doc['processing_error']['code'] == 'OCR_FAILED'
        assert 'private internal error' not in json.dumps(doc)
        assert doc['pages'][0]['raw_text'] and doc['pages'][0]['ocr_json']['raw_results']
        assert doc['pages'][1]['ocr_json'] == {'status': 'pending'}
        assert doc['sections'] == []
        assert (settings.ocr_result_dir/'1/page-0001.json').is_file()
        assert len(list(settings.upload_dir.glob('*.pdf'))) == 1


def test_malformed_ocr_is_saved_before_validation(pipeline_factory):
    app, settings = pipeline_factory(FakeOcr(malformed=True))
    with TestClient(app) as client:
        upload(client)
        doc = client.get('/api/documents/1').json()
        assert doc['ocr_status'] == 'failed'
        assert doc['pages'][0]['ocr_json']['raw_results'][0]['res']['rec_texts']
        assert (settings.ocr_result_dir/'1/page-0001.json').is_file()


def test_parser_failure_keeps_all_raw_and_no_partial_structure(pipeline_factory):
    class BrokenParser:
        def parse(self, pages):
            assert len(pages) == 2
            raise ValueError('parse failure')
    app, settings = pipeline_factory(parser=BrokenParser())
    with TestClient(app) as client:
        upload(client)
        doc = client.get('/api/documents/1').json()
        assert doc['ocr_status'] == 'completed' and doc['parse_status'] == 'failed'
        assert doc['processing_error']['code'] == 'PARSING_FAILED'
        assert all(page['raw_text'] for page in doc['pages'])
        assert len(list((settings.ocr_result_dir/'1').glob('page-*.json'))) == 2
        assert doc['sections'] == doc['handover_items'] == []


def test_empty_ocr_does_not_invent_content(pipeline_factory):
    app, _ = pipeline_factory(FakeOcr(blank=True))
    with TestClient(app) as client:
        upload(client)
        doc = client.get('/api/documents/1').json()
        assert doc['ocr_status'] == doc['parse_status'] == 'completed'
        assert doc['sections'] == doc['handover_items'] == []
        assert all(page['ocr_json']['lines'] == [] for page in doc['pages'])


def test_restart_marks_interrupted_jobs_failed(pipeline_factory):
    app, settings = pipeline_factory()
    engine = create_db_engine(settings.database_url)
    with Session(engine) as session:
        session.add(Document(title='interrupted', document_type='handover', source_filename='old.pdf', source_path='old.pdf', ocr_status='processing'))
        session.commit()
    engine.dispose()
    with TestClient(app) as client:
        doc = client.get('/api/documents/1').json()
        assert doc['ocr_status'] == doc['parse_status'] == 'failed'
        assert doc['processing_error']['code'] == 'PROCESSING_INTERRUPTED'


def test_duplicate_filenames_have_distinct_storage(pipeline_factory):
    app, settings = pipeline_factory(FakeOcr(blank=True))
    with TestClient(app) as client:
        assert upload(client).json()['document_id'] == 1
        assert upload(client).json()['document_id'] == 2
        assert len(list(settings.upload_dir.glob('*.pdf'))) == 2


def test_structure_database_failure_rolls_back_partial_sections(pipeline_factory):
    from app.parsing.section_mapper import ParsedSection
    class InvalidParser:
        def parse(self, pages):
            return [ParsedSection('overview', '개요', '본문', 1, 1),
                    ParsedSection('other', None, 'invalid required title', 2, 2)]
    app, _ = pipeline_factory(parser=InvalidParser())
    with TestClient(app) as client:
        upload(client)
        doc = client.get('/api/documents/1').json()
        assert doc['ocr_status'] == 'completed' and doc['parse_status'] == 'failed'
        assert doc['sections'] == doc['handover_items'] == []
        assert len(doc['pages']) == 2
