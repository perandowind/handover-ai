"""Real PDF upload -> PaddleOCR -> parser -> SQLite; never INSERT metadata.

Run from backend: uv run python scripts/run_seed_pipeline.py
The new isolated run directory preserves the DB, page images and native raw OCR.
Exit 1 means ground truth or pipeline validation failed. No LLM task is invoked.
"""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
from datetime import datetime, timezone

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.main import create_app
from scripts.seed_validation import compare_document, sha256

SAMPLES = BACKEND.parent / 'sample-data'


def run(run_dir: Path) -> dict:
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    database_url = f'sqlite:///{run_dir / "app.db"}'
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=BACKEND,
                   env={**os.environ, 'DATABASE_URL': database_url}, check=True)
    settings = Settings(_env_file=None, database_url=database_url, upload_dir=run_dir/'uploads',
                        page_image_dir=run_dir/'pages', ocr_result_dir=run_dir/'ocr', export_dir=run_dir/'exports')
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'mode': 'real_paddleocr',
              'artifact_directory': str(run_dir), 'database_url': database_url,
              'models': [settings.ocr_detection_model, settings.ocr_recognition_model],
              'render_dpi': settings.pdf_render_dpi,
              'versions': {p: importlib.metadata.version(p) for p in ['paddleocr','paddlepaddle','PyMuPDF']},
              'documents': []}
    with TestClient(create_app(settings)) as client:
        for metadata_path in sorted((SAMPLES/'metadata').glob('seed-*.expected.json')):
            expected = json.loads(metadata_path.read_text())
            pdf = SAMPLES/'scanned-pdfs'/expected['pdf']
            print(f"Processing {pdf.name}", flush=True)
            with pdf.open('rb') as source:
                response = client.post('/api/documents/upload', files={'file': (pdf.name, source, 'application/pdf')})
            if response.status_code != 202:
                result = {'seed_id': expected['id'], 'passed': False, 'upload_error': response.json()}
            else:
                doc = client.get(f"/api/documents/{response.json()['document_id']}").json()
                (run_dir/f"{expected['id']}.document.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2))
                result = compare_document(doc, expected, settings.ocr_result_dir, settings.page_image_dir)
            result.update(pdf_sha256=sha256(pdf), metadata_sha256=sha256(metadata_path))
            report['documents'].append(result)
            report['passed'] = len(report['documents']) == 5 and all(d['passed'] for d in report['documents'])
            (run_dir/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
            print(f"{expected['id']}: passed={result['passed']} keywords={result.get('keyword_matched')}/{result.get('keyword_total')}", flush=True)
    with sqlite3.connect(f'file:{run_dir / "app.db"}?mode=ro', uri=True) as db:
        report['database_counts'] = {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                                     for table in ('documents','document_pages','document_sections','handover_items','questions','scoring_results')}
        report['foreign_key_violations'] = db.execute('PRAGMA foreign_key_check').fetchall()
        report['item_document_mismatches'] = db.execute(
            'SELECT COUNT(*) FROM handover_items h JOIN document_sections s ON h.section_id=s.id '
            'WHERE h.document_id != s.document_id').fetchone()[0]
    report['passed'] &= (not report['foreign_key_violations'] and report['item_document_mismatches'] == 0
                         and report['database_counts']['documents'] == 5
                         and report['database_counts']['document_pages'] == 10
                         and report['database_counts']['questions'] == report['database_counts']['scoring_results'] == 0)
    (run_dir/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, default=BACKEND/'data/seed-runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    args = parser.parse_args()
    result = run(args.run_dir)
    print(f"Report: {args.run_dir.resolve() / 'report.json'}", flush=True)
    raise SystemExit(0 if result['passed'] else 1)

if __name__ == '__main__':
    main()
