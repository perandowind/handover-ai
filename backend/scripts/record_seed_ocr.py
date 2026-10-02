"""Export reduced real OCR recordings for offline regression, not seed DB insertion.

uv run python scripts/record_seed_ocr.py data/seed-runs/<successful-run>
Native unmodified raw OCR remains in the run directory. Only the three recognizer
arrays consumed by normalize_results are copied into the checked-in fixtures.
"""
import argparse
import json
from pathlib import Path
import sys
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from scripts.run_seed_pipeline import SAMPLES
from scripts.seed_validation import sha256


def export(run_dir: Path):
    report = json.loads((run_dir/'report.json').read_text())
    if report['mode'] != 'real_paddleocr' or not report['passed']:
        raise ValueError('Require a successful real OCR report')
    output = SAMPLES/'ocr-recordings'
    output.mkdir(exist_ok=True)
    for item in report['documents']:
        seed = item['seed_id']
        pdf = SAMPLES/'scanned-pdfs'/f'{seed}.pdf'
        if item['pdf_sha256'] != sha256(pdf):
            raise ValueError('PDF changed since OCR capture')
        doc = json.loads((run_dir/f'{seed}.document.json').read_text())
        pages=[]
        for page in doc['pages']:
            reduced=[]
            for raw in page['ocr_json']['raw_results']:
                res=raw.get('res',raw)
                reduced.append({'res':{key:res[key] for key in ('rec_texts','rec_scores','rec_polys')}})
            pages.append({'page_number':page['page_number'],'raw_results':reduced})
        recording={'origin':'real_paddleocr','captured_at':report['created_at'],
                   'models':report['models'],'versions':report['versions'],
                   'pdf_sha256':item['pdf_sha256'],'pages':pages}
        (output/f'{seed}.json').write_text(json.dumps(recording,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir',type=Path)
    export(parser.parse_args().run_dir.resolve())
