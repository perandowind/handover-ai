"""Real PaddleOCR smoke test; keeps all artifacts in an isolated run directory.

Run from backend: uv run python scripts/smoke_document_pipeline.py
No mock OCR, no canonical-metadata INSERT, no changes to data/app.db.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make direct script execution work without an editable package installation.
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def main():
    root = BACKEND / 'data/smoke' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    root.mkdir(parents=True)
    database_url = f'sqlite:///{root / "app.db"}'
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=BACKEND,
                   env={**os.environ, 'DATABASE_URL': database_url}, check=True)
    settings = Settings(database_url=database_url, upload_dir=root/'uploads',
                        page_image_dir=root/'pages', ocr_result_dir=root/'ocr')
    sample = BACKEND.parent / 'sample-data/scanned-pdfs/db-handover-scan.pdf'
    with TestClient(create_app(settings)) as client:
        with sample.open('rb') as source:
            response = client.post('/api/documents/upload', files={'file': (sample.name, source, 'application/pdf')})
        assert response.status_code == 202, response.text
        document_id = response.json()['document_id']
        doc = client.get(f'/api/documents/{document_id}').json()
        (root/'document.json').write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
        assert doc['ocr_status'] == doc['parse_status'] == 'completed', doc['processing_error']
        assert len(doc['pages']) == 2
        types = {section['section_type'] for section in doc['sections']}
        assert {'overview', 'responsibilities', 'systems', 'procedures', 'precautions',
                'troubleshooting', 'contacts', 'references'} <= types, types
        assert doc['handover_items']
        for page in doc['pages']:
            saved = json.loads((root/'ocr'/str(document_id)/f'page-{page["page_number"]:04}.json').read_text())
            assert saved == page['ocr_json']
            assert saved['raw_results'] and saved['lines']
            assert all('text' in line and 'confidence' in line and len(line['bbox']) == 4 for line in saved['lines'])
        report = {'result': 'passed', 'upload_http_status': 202,
                  'ocr_status': doc['ocr_status'], 'parse_status': doc['parse_status'],
                  'pages': len(doc['pages']), 'sections': len(doc['sections']),
                  'handover_items': len(doc['handover_items']),
                  'ocr_lines': [len(page['ocr_json']['lines']) for page in doc['pages']],
                  'artifact_directory': str(root)}
        (root/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
