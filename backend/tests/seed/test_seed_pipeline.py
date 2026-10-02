"""Seed regression uses recorded real OCR, never ground truth as OCR input.

RUN_REAL_SEED_OCR=1 additionally enables the actual PaddleOCR integration test.
"""
import json
import os
from pathlib import Path
import sqlite3

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from scripts.run_seed_pipeline import run, SAMPLES
from scripts.seed_validation import compare_document, sha256

SEEDS = ['backend', 'database', 'infrastructure', 'network', 'operations']


class RecordedOcr:
    def __init__(self, recording):
        self.recording = recording
        self.calls = 0

    def recognize(self, image_path):
        self.calls += 1
        page = int(image_path.stem.split('-')[-1])
        assert image_path.is_file()
        return self.recording['pages'][page-1]['raw_results']


@pytest.mark.parametrize('name', SEEDS)
def test_seed_image_pdf_contract(name):
    pdf = SAMPLES/'scanned-pdfs'/f'seed-{name}.pdf'
    source = json.loads((SAMPLES/'sources'/f'seed-{name}.json').read_text())
    metadata = json.loads((SAMPLES/'metadata'/f'seed-{name}.expected.json').read_text())
    assert source['synthetic'] is metadata['synthetic'] is True
    assert len(source['sections']) == len(metadata['sections']) == 8
    assert len({s['section_type'] for s in metadata['sections']}) == 8
    assert all(s['expected_keywords'] for s in metadata['sections'])
    with pymupdf.open(pdf) as doc:
        assert len(doc) == metadata['expected_pages'] == 2
        assert all(page.get_images() and not page.get_text().strip() for page in doc)


@pytest.mark.parametrize('name', SEEDS)
def test_seed_recorded_ocr_to_sqlite(name, tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from app.core.config import BACKEND_DIR, get_settings
    metadata = json.loads((SAMPLES/'metadata'/f'seed-{name}.expected.json').read_text())
    pdf = SAMPLES/'scanned-pdfs'/metadata['pdf']
    recording = json.loads((SAMPLES/'ocr-recordings'/f'seed-{name}.json').read_text())
    assert recording['origin'] == 'real_paddleocr'
    assert recording['pdf_sha256'] == sha256(pdf), 'Re-record after changing a PDF'
    url = f'sqlite:///{tmp_path/"seed.db"}'
    monkeypatch.setenv('DATABASE_URL', url)
    get_settings.cache_clear()
    try:
        command.upgrade(Config(str(BACKEND_DIR/'alembic.ini')), 'head')
    finally:
        get_settings.cache_clear()
    settings = Settings(_env_file=None, database_url=url, upload_dir=tmp_path/'uploads',
                        page_image_dir=tmp_path/'pages', ocr_result_dir=tmp_path/'ocr')
    engine = RecordedOcr(recording)
    with TestClient(create_app(settings, ocr_engine=engine)) as client:
        response = client.post('/api/documents/upload', files={'file': (pdf.name,pdf.read_bytes(),'application/pdf')})
        assert response.status_code == 202
        doc = client.get(f"/api/documents/{response.json()['document_id']}").json()
        assert engine.calls == 2
        result = compare_document(doc, metadata, settings.ocr_result_dir, settings.page_image_dir)
        assert result['passed'], result
        # Mutation checks prove comparison rejects absent or incorrectly mapped sections.
        doc['sections'] = [s for s in doc['sections'] if s['section_type'] != 'systems']
        assert not compare_document(doc, metadata, settings.ocr_result_dir, settings.page_image_dir)['passed']
    with sqlite3.connect(f'file:{tmp_path / "seed.db"}?mode=ro', uri=True) as db:
        assert db.execute('SELECT COUNT(*) FROM documents').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM document_pages').fetchone()[0] == 2
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert db.execute('SELECT COUNT(*) FROM questions').fetchone()[0] == 0


@pytest.mark.skipif(os.environ.get('RUN_REAL_SEED_OCR') != '1', reason='Opt-in real PaddleOCR: RUN_REAL_SEED_OCR=1')
def test_real_seed_pipeline(tmp_path):
    result = run(tmp_path/'real-seed-run')
    assert result['passed'], result
    assert len(result['documents']) == 5
