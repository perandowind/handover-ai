"""Read-only ground truth comparison. Metadata is never a persistence input."""
import hashlib
import json
import re
from pathlib import Path


def normalized(text: str) -> str:
    return re.sub(r'\s+', '', text).casefold()


def compare_document(document: dict, expected: dict, ocr_dir: Path, page_dir: Path) -> dict:
    checks = []
    for target in expected['sections']:
        matching = [s for s in document['sections'] if s['section_type'] == target['section_type']]
        content = normalized('\n'.join(s['content'] for s in matching))
        found = [k for k in target['expected_keywords'] if normalized(k) in content]
        checks.append({'section_type': target['section_type'], 'present': bool(matching),
                       'source_page_matches': any(s['source_page'] == target['source_page'] for s in matching),
                       'matched_keywords': found,
                       'missing_keywords': [k for k in target['expected_keywords'] if k not in found]})
    total = sum(len(s['expected_keywords']) for s in expected['sections'])
    matched = sum(len(s['matched_keywords']) for s in checks)
    raw_preserved = len(document['pages']) == expected['expected_pages']
    line_counts = []
    for page in document['pages']:
        saved = ocr_dir / str(document['id']) / f"page-{page['page_number']:04}.json"
        payload = page['ocr_json']
        lines = payload.get('lines', [])
        line_counts.append(len(lines))
        raw_preserved &= (saved.is_file() and json.loads(saved.read_text()) == payload
                          and bool(payload.get('raw_results')) and bool(lines)
                          and (page_dir / str(document['id']) / f"page-{page['page_number']:04}.png").is_file()
                          and all(isinstance(line.get('text'), str) and 0 <= line.get('confidence', -1) <= 1
                                  and len(line.get('bbox', [])) == 4 for line in lines))
    section_ids = {s['id'] for s in document['sections']}
    links_valid = all(s['document_id'] == document['id'] for s in document['sections']) and all(item['section_id'] in section_ids
                      for item in document['handover_items'])
    title_found = normalized(expected['title']) in normalized('\n'.join(p['raw_text'] for p in document['pages']))
    passed = (document['ocr_status'] == document['parse_status'] == 'completed'
              and raw_preserved and links_valid and title_found
              and len(document['handover_items']) >= expected['minimum_items']
              and all(s['present'] and s['source_page_matches'] for s in checks)
              and matched / total >= expected['minimum_keyword_recall'])
    return {'seed_id': expected['id'], 'domain': expected['domain'], 'title': expected['title'],
            'document_id': document['id'], 'passed': bool(passed),
            'ocr_status': document['ocr_status'], 'parse_status': document['parse_status'],
            'pages': len(document['pages']), 'sections': len(document['sections']),
            'handover_items': len(document['handover_items']), 'ocr_lines': line_counts,
            'title_found': title_found, 'raw_preserved': bool(raw_preserved), 'links_valid': links_valid,
            'keyword_matched': matched, 'keyword_total': total, 'keyword_recall': matched / total,
            'section_checks': checks, 'processing_error': document.get('processing_error')}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
