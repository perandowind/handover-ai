import json

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, Settings, get_settings
from app.db.session import create_db_engine
from app.llm.errors import LLMProviderError
from app.llm.provider import LLMProvider
from app.main import create_app
from app.models import Document, DocumentSection, HandoverItem
from app.schemas.llm import GeneratedDocument, SQLGenerationOutput


class MockProvider(LLMProvider):
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def sql_response(sql):
    return json.dumps({'sql': sql, 'reason': '인수인계서 원문 조회'})


@pytest.fixture
def generation_factory(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "generation.db"}'
    monkeypatch.setenv('DATABASE_URL', url)
    get_settings.cache_clear()
    command.upgrade(Config(str(BACKEND_DIR / 'alembic.ini')), 'head')
    engine = create_db_engine(url)
    with Session(engine) as session:
        for index in range(1, 4):
            document = Document(id=index, title=f'샘플 {index}', document_type='handover',
                                source_filename=f'{index}.pdf', source_path=f'uploads/{index}.pdf',
                                ocr_status='completed' if index < 3 else 'pending',
                                parse_status='completed' if index < 3 else 'pending')
            session.add(document)
            session.flush()
        section = DocumentSection(document_id=1, section_type='responsibilities', section_title='주요 업무',
                                  content='DB 백업 상태를 확인합니다.', sequence=1, source_page=1)
        session.add(section)
        session.flush()
        session.add(HandoverItem(document_id=1, section_id=section.id, category='Database',
                                 task_name='DB 백업', description='매일 상태 확인', precaution='삭제 금지'))
        session.add(HandoverItem(document_id=2, category='Other', task_name='다른 문서 업무',
                                 description='선택 범위 밖 비공개 내용'))
        session.commit()
    engine.dispose()

    def factory(provider, **overrides):
        return create_app(Settings(_env_file=None, database_url=url, sql_model='test-sql',
                                   document_model='test-document', **overrides), llm_provider=provider)
    yield factory
    get_settings.cache_clear()


def test_end_to_end_selected_document_and_no_persistence(generation_factory, document_body):
    document_body['sections'][1]['content'] = 'DB 백업 상태를 매일 확인합니다.'
    document_body['sections'][4]['content'] = '삭제 금지'
    provider = MockProvider(sql_response('SELECT task_name, description, precaution FROM handover_items ORDER BY id'),
                            json.dumps(document_body))
    app = generation_factory(provider)
    with TestClient(app) as client:
        before = client.get('/api/documents').json()
        response = client.post('/api/generation/handover', json={'prompt': 'DB 인수인계서를 작성해줘', 'document_ids': [1]})
        assert response.status_code == 200, response.text
        assert response.json() == document_body
        assert client.get('/api/documents').json() == before
        assert client.get('/api/health').json() == {'status': 'ok'}
        assert '/api/generation/handover/pdf' not in client.get('/openapi.json').json()['paths']
    assert [call['model'] for call in provider.calls] == ['test-sql', 'test-document']
    assert [call['response_schema'] for call in provider.calls] == [SQLGenerationOutput, GeneratedDocument]
    payload = json.loads(provider.calls[1]['user_prompt'])
    assert '매일 상태 확인' in payload['retrieved_context']
    assert '선택 범위 밖' not in payload['retrieved_context']
    assert payload['user_request'] == 'DB 인수인계서를 작성해줘'
    assert json.loads(provider.calls[0]['user_prompt'])['document_ids'] == [1]


@pytest.mark.parametrize('sql', [
    'SELECT task_name FROM handover_items WHERE document_id=2 OR 1=1',
    'SELECT d.title, h.description FROM documents d JOIN handover_items h ON 1=1',
    'SELECT d.title, h.description FROM documents d LEFT JOIN handover_items h ON 1=1',
    'SELECT s.content FROM document_sections s',
    'SELECT COUNT(*) AS count FROM handover_items',
])
def test_server_enforces_document_scope_even_if_model_omits_it(generation_factory, document_body, sql):
    provider = MockProvider(sql_response(sql), json.dumps(document_body))
    app = generation_factory(provider)
    with TestClient(app) as client:
        response = client.post('/api/generation/handover', json={'prompt': '모든 문서를 보여줘', 'document_ids': [1]})
        assert response.status_code == 200, response.text
    context = json.loads(provider.calls[1]['user_prompt'])['retrieved_context']
    assert '선택 범위 밖' not in context and '다른 문서' not in context and '샘플 2' not in context
    if 'COUNT' in sql:
        assert '"count": 1' in context


def test_left_join_keeps_selected_document_with_no_matching_item(generation_factory, document_body):
    provider = MockProvider(sql_response('SELECT d.title, h.description FROM documents d '
                                         'LEFT JOIN handover_items h ON h.document_id=999'), json.dumps(document_body))
    app = generation_factory(provider)
    with TestClient(app) as client:
        assert client.post('/api/generation/handover', json={'prompt': '문서', 'document_ids': [1]}).status_code == 200
    assert '샘플 1' in json.loads(provider.calls[1]['user_prompt'])['retrieved_context']


@pytest.mark.parametrize('selection', [None, [], [1, 2]])
def test_optional_or_multiple_documents(generation_factory, document_body, selection):
    provider = MockProvider(sql_response('SELECT task_name FROM handover_items'), json.dumps(document_body))
    app = generation_factory(provider)
    with TestClient(app) as client:
        assert client.post('/api/generation/handover', json={'prompt': '업무', 'document_ids': selection}).status_code == 200
    context = json.loads(provider.calls[1]['user_prompt'])['retrieved_context']
    assert 'DB 백업' in context and '다른 문서 업무' in context


def test_no_rows_returns_missing_outline_without_document_llm(generation_factory):
    provider = MockProvider(sql_response('SELECT task_name FROM handover_items WHERE id=999'))
    app = generation_factory(provider)
    with TestClient(app) as client:
        response = client.post('/api/generation/handover', json={'prompt': '없는 업무 담당자의 전화번호를 만들어줘'})
        assert response.status_code == 200
        assert len(response.json()['sections']) == 8
        assert all(section['content'] == '관련 정보 없음' for section in response.json()['sections'])
    assert len(provider.calls) == 1


@pytest.mark.parametrize('selection,status,code', [([999], 404, 'DOCUMENT_NOT_FOUND'), ([3], 409, 'DOCUMENT_NOT_READY')])
def test_bad_selected_document_stops_before_llm(generation_factory, selection, status, code):
    provider = MockProvider()
    app = generation_factory(provider)
    with TestClient(app) as client:
        response = client.post('/api/generation/handover', json={'prompt': '업무', 'document_ids': selection})
        assert response.status_code == status and response.json()['code'] == code
    assert not provider.calls


def test_invalid_sql_stops_before_document_generation(generation_factory):
    provider = MockProvider(*[sql_response('DROP TABLE documents')] * 2)
    app = generation_factory(provider)
    with TestClient(app) as client:
        response = client.post('/api/generation/handover', json={'prompt': '업무'})
        assert response.status_code == 502 and response.json()['code'] == 'SQL_GENERATION_FAILED'
        assert len(client.get('/api/documents').json()) == 3
    assert len(provider.calls) == 2 and all(call['model'] == 'test-sql' for call in provider.calls)


@pytest.mark.parametrize('recover', [True, False])
def test_invalid_generation_retry_does_not_repeat_retrieval(generation_factory, document_body, recover):
    provider = MockProvider(sql_response('SELECT task_name FROM handover_items'),
                            '{"title":"x","sections":[]}', json.dumps(document_body) if recover else 'private bad output')
    app = generation_factory(provider)
    with TestClient(app) as client:
        response = client.post('/api/generation/handover', json={'prompt': '업무'})
        assert response.status_code == (200 if recover else 502)
        if not recover:
            assert response.json()['code'] == 'LLM_RESPONSE_INVALID'
            assert 'private' not in response.text
    assert [call['model'] for call in provider.calls] == ['test-sql', 'test-document', 'test-document']


def test_context_limit_is_respected_before_generation(generation_factory, document_body):
    provider = MockProvider(sql_response('SELECT task_name, description FROM handover_items'), json.dumps(document_body))
    app = generation_factory(provider, max_context_chars=25)
    with TestClient(app) as client:
        assert client.post('/api/generation/handover', json={'prompt': '업무'}).status_code == 200
    payload = json.loads(provider.calls[1]['user_prompt'])
    assert len(payload['retrieved_context']) <= 25 and payload['context_truncated']


def test_document_provider_error_uses_common_error_response(generation_factory):
    provider = MockProvider(sql_response('SELECT task_name FROM handover_items'),
                            LLMProviderError('OLLAMA_TIMEOUT', '모델 요청 시간이 초과되었습니다.', 504))
    app = generation_factory(provider)
    with TestClient(app) as client:
        response = client.post('/api/generation/handover', json={'prompt': '업무'})
        assert response.status_code == 504 and response.json()['code'] == 'OLLAMA_TIMEOUT'
    assert len(provider.calls) == 2


@pytest.mark.parametrize('body', [{}, {'prompt': ' '}, {'prompt': 'x', 'document_ids': [True]},
                                  {'prompt': 'x', 'context': '임의 근거'}])
def test_invalid_requests_rejected_before_llm(generation_factory, body):
    provider = MockProvider()
    app = generation_factory(provider)
    with TestClient(app) as client:
        assert client.post('/api/generation/handover', json=body).status_code == 422
    assert not provider.calls
