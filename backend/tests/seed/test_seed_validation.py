import json
import pytest
from scripts.seed_validation import compare_document, normalized


@pytest.fixture
def example(tmp_path):
    payload = {'raw_results': [{'res': {'rec_texts': ['업무 개요', '백업 확인']}}],
               'lines': [{'text': '백업 확인', 'confidence': .9, 'bbox': [[0,0],[1,0],[1,1],[0,1]]}]}
    (tmp_path/'ocr/1').mkdir(parents=True)
    (tmp_path/'pages/1').mkdir(parents=True)
    (tmp_path/'ocr/1/page-0001.json').write_text(json.dumps(payload))
    (tmp_path/'pages/1/page-0001.png').write_bytes(b'unit-test-placeholder')
    expected = {'id': 'unit', 'domain': 'Database', 'title': '테스트', 'expected_pages': 1,
                'sections': [{'section_type':'overview','source_page':1,'expected_keywords':['백업 확인']}],
                'minimum_items':1, 'minimum_keyword_recall':.9}
    doc = {'id':1, 'ocr_status':'completed', 'parse_status':'completed',
           'pages':[{'page_number':1,'raw_text':'테스트\n백업 확인','ocr_json':payload}],
           'sections':[{'id':1,'document_id':1,'section_type':'overview','source_page':1,'content':'백업 확인'}],
           'handover_items':[{'section_id':1}]}
    return doc, expected, tmp_path


def test_whitespace_normalization_only():
    assert normalized('  PostgreSQL\n 백업 ') == 'postgresql백업'
    assert normalized('백업') != normalized('백엽')


def test_comparison_success(example):
    doc, expected, root = example
    assert compare_document(doc, expected, root/'ocr', root/'pages')['passed']


@pytest.mark.parametrize('failure', ['keyword', 'page', 'title', 'status', 'raw', 'link', 'image'])
def test_comparison_rejects_regressions(example, failure):
    doc, expected, root = example
    if failure == 'keyword': doc['sections'][0]['content'] = '관련 정보 없음'
    if failure == 'page': doc['sections'][0]['source_page'] = 2
    if failure == 'title': doc['pages'][0]['raw_text'] = '다른 문서'
    if failure == 'status': doc['parse_status'] = 'failed'
    if failure == 'raw': (root/'ocr/1/page-0001.json').write_text('{}')
    if failure == 'link': doc['handover_items'][0]['section_id'] = 999
    if failure == 'image': (root/'pages/1/page-0001.png').unlink()
    assert not compare_document(doc, expected, root/'ocr', root/'pages')['passed']
