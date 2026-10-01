import json

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, Settings, get_settings
from app.core.exceptions import AppError
from app.db.session import create_db_engine
from app.llm.errors import LLMProviderError
from app.llm.provider import LLMProvider
from app.main import create_app
from app.models import Document, DocumentSection, HandoverItem
from app.retrieval.executor import SQLiteReader
from app.retrieval.schema import RetrievalSchema
from app.retrieval.validator import SQLValidator, ValidatedSQL


class MockProvider(LLMProvider):
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def sql_response(sql):
    return json.dumps({'sql': sql, 'reason': '관련 업무 검색'}, ensure_ascii=False)


@pytest.fixture
def retrieval_factory(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "retrieval.db"}'
    monkeypatch.setenv('DATABASE_URL', url)
    get_settings.cache_clear()
    command.upgrade(Config(str(BACKEND_DIR / 'alembic.ini')), 'head')
    engine = create_db_engine(url)
    with Session(engine) as session:
        document = Document(title='DB 인수인계', document_type='handover', source_filename='scan.pdf',
                            source_path='uploads/scan.pdf', ocr_status='completed', parse_status='completed')
        session.add(document)
        session.flush()
        section = DocumentSection(document_id=document.id, section_type='responsibilities',
                                  section_title='주요 업무', content='백업 및 모니터링', sequence=1, source_page=1)
        session.add(section)
        session.flush()
        for index, name in enumerate(['DB 백업', 'DB 복원', '서버 모니터링']):
            session.add(HandoverItem(document_id=document.id, section_id=section.id, category='Database',
                                    task_name=name, description=f'{name} 설명', precaution='삭제 금지',
                                    importance=5-index))
        session.commit()
    engine.dispose()

    def factory(provider, **overrides):
        settings = Settings(_env_file=None, database_url=url, sql_model='mock-sql-model', **overrides)
        return create_app(settings, llm_provider=provider), settings
    yield factory
    get_settings.cache_clear()


def test_natural_language_to_sql_to_db_to_context(retrieval_factory):
    provider = MockProvider(sql_response("SELECT h.document_id, h.task_name, h.description, h.precaution, s.source_page "
        "FROM handover_items h JOIN document_sections s ON s.id=h.section_id "
        "WHERE h.task_name LIKE '%DB%' ORDER BY h.importance DESC"))
    app, _ = retrieval_factory(provider)
    with TestClient(app) as client:
        assert provider.calls == []
        response = client.post('/api/retrieval/search', json={'query': 'DB 운영 업무를 찾아줘'})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['row_count'] == 2
        assert [row['task_name'] for row in body['rows']] == ['DB 백업', 'DB 복원']
        assert body['rows'][0]['source_page'] == 1
        assert '업무명: "DB 백업"' in body['context'] and '주의사항: "삭제 금지"' in body['context']
        assert body['context_truncated'] is False
        assert body['sql'].endswith('LIMIT 100')
        assert client.get('/api/health').json() == {'status': 'ok'}
    assert len(provider.calls) == 1 and provider.calls[0]['model'] == 'mock-sql-model'
    prompt = json.loads(provider.calls[0]['user_prompt'])
    assert 'document_sections(' in prompt['schema'] and 'source_page INTEGER' in prompt['schema']
    assert prompt['request'] == 'DB 운영 업무를 찾아줘'


@pytest.mark.parametrize('first', [
    sql_response('DROP TABLE documents'),
    sql_response('SELECT missing FROM handover_items'),
    'not JSON', '{"sql":123,"reason":"x"}',
])
def test_one_regeneration_and_invalid_sql_never_reaches_executor(retrieval_factory, monkeypatch, first):
    provider = MockProvider(first, sql_response('SELECT task_name FROM handover_items ORDER BY importance DESC'))
    app, _ = retrieval_factory(provider)
    with TestClient(app) as client:
        reader = app.state.retrieval_service.strategy.reader
        original = reader.execute
        executed = []
        def record(query):
            executed.append(query)
            return original(query)
        monkeypatch.setattr(reader, 'execute', record)
        response = client.post('/api/retrieval/search', json={'query': '업무 검색'})
        assert response.status_code == 200
        assert len(executed) == 1 and isinstance(executed[0], ValidatedSQL)
        assert 'DROP' not in executed[0].sql and 'missing' not in executed[0].sql
        assert len(client.get('/api/documents').json()) == 1
    assert len(provider.calls) == 2
    assert json.loads(provider.calls[1]['user_prompt'])['previous_validation_error']


@pytest.mark.parametrize('responses', [
    [sql_response('DROP TABLE documents')] * 2,
    ['broken JSON', sql_response('DELETE FROM documents')],
    [sql_response('SELECT missing FROM documents'), 'broken JSON'],
])
def test_retry_budget_is_two_total_and_no_sql_on_failure(retrieval_factory, monkeypatch, responses):
    provider = MockProvider(*responses)
    app, _ = retrieval_factory(provider)
    with TestClient(app) as client:
        def forbidden(*args):
            pytest.fail('No DB query may run before successful validation')
        monkeypatch.setattr(app.state.retrieval_service.strategy.reader, 'execute', forbidden)
        response = client.post('/api/retrieval/search', json={'query': '업무 검색'})
        assert response.status_code == 502
        assert response.json()['code'] == 'SQL_GENERATION_FAILED'
        assert response.json()['detail']['attempts'] == 2
    assert len(provider.calls) == 2


def test_limits_empty_results_and_aggregate(retrieval_factory):
    provider = MockProvider(
        sql_response('SELECT task_name, description FROM handover_items ORDER BY importance DESC LIMIT 9000'),
        sql_response('SELECT task_name FROM handover_items WHERE id=999'),
        sql_response('SELECT COUNT(*) AS count FROM handover_items'),
        sql_response('SELECT task_name FROM handover_items LIMIT 0'),
    )
    app, _ = retrieval_factory(provider, max_retrieval_rows=1, max_context_chars=25)
    with TestClient(app) as client:
        body = client.post('/api/retrieval/search', json={'query': '검색'}).json()
        assert body['row_count'] == 1 and body['rows'][0]['task_name'] == 'DB 백업'
        assert body['sql'].endswith('LIMIT 1')
        assert len(body['context']) <= 25 and body['context_truncated']
        empty = client.post('/api/retrieval/search', json={'query': '없음'}).json()
        assert empty['rows'] == [] and empty['context'] == '' and not empty['context_truncated']
        aggregate = client.post('/api/retrieval/search', json={'query': '몇 개?'}).json()
        assert aggregate['rows'] == [{'count': 3}]
        assert client.post('/api/retrieval/search', json={'query': '0개'}).json()['rows'] == []


def test_provider_failure_is_not_retried(retrieval_factory):
    provider = MockProvider(LLMProviderError('OLLAMA_UNAVAILABLE', 'Unavailable', 503))
    app, _ = retrieval_factory(provider)
    with TestClient(app) as client:
        response = client.post('/api/retrieval/search', json={'query': '검색'})
        assert response.status_code == 503 and response.json()['code'] == 'OLLAMA_UNAVAILABLE'
    assert len(provider.calls) == 1


@pytest.mark.parametrize('body', [{}, {'query': ''}, {'query': '  '}, {'query': 'x'*4001},
                                  {'query': '검색', 'sql': 'SELECT * FROM documents'}])
def test_invalid_request_never_calls_provider(retrieval_factory, body):
    provider = MockProvider()
    app, _ = retrieval_factory(provider)
    with TestClient(app) as client:
        assert client.post('/api/retrieval/search', json=body).status_code == 422
    assert not provider.calls


@pytest.mark.parametrize('sql', [
    'DELETE FROM documents', 'DROP TABLE documents', 'PRAGMA table_info(documents)',
    "ATTACH DATABASE ':memory:' AS another", 'SELECT * FROM sqlite_master',
    'SELECT * FROM questions', "SELECT load_extension('anything') FROM documents",
])
def test_executor_readonly_defense_even_if_validator_is_bypassed(retrieval_factory, sql):
    _, settings = retrieval_factory(MockProvider())
    reader = SQLiteReader(settings.database_url, RetrievalSchema(), 100)
    # A deliberately forged token probes the independent runtime guard.
    with pytest.raises(AppError) as error:
        reader.execute(ValidatedSQL(sql, 100))
    assert error.value.code == 'RETRIEVAL_FAILED'
    valid = SQLValidator(RetrievalSchema()).validate('SELECT id FROM documents')
    assert len(reader.execute(valid)) == 1


def test_executor_rejects_raw_strings_and_missing_db(tmp_path):
    reader = SQLiteReader(f'sqlite:///{tmp_path / "missing.db"}', RetrievalSchema(), 100)
    with pytest.raises(TypeError):
        reader.execute('SELECT * FROM documents')
    with pytest.raises(AppError):
        reader.execute(SQLValidator(RetrievalSchema()).validate('SELECT id FROM documents'))
    assert not (tmp_path / 'missing.db').exists()


def test_database_execution_error_does_not_trigger_regeneration(retrieval_factory, monkeypatch):
    provider = MockProvider(sql_response('SELECT task_name FROM handover_items'))
    app, _ = retrieval_factory(provider)
    with TestClient(app) as client:
        def unavailable(*args):
            raise AppError('RETRIEVAL_FAILED', 'Unavailable', 503)
        monkeypatch.setattr(app.state.retrieval_service.strategy.reader, 'execute', unavailable)
        assert client.post('/api/retrieval/search', json={'query': '검색'}).status_code == 503
    assert len(provider.calls) == 1


def test_progress_deadline_interrupts_expensive_reads(retrieval_factory, monkeypatch):
    import app.retrieval.executor as executor

    _, settings = retrieval_factory(MockProvider())
    reader = SQLiteReader(settings.database_url, RetrievalSchema(), 100)
    ticks = iter([0, 100])
    monkeypatch.setattr(executor.time, 'monotonic', lambda: next(ticks, 100))
    # Force enough VM steps to exercise the deadline, independent of wall time.
    sql = 'SELECT COUNT(*) AS n FROM ' + ', '.join(f'handover_items AS h{i}' for i in range(10))
    with pytest.raises(AppError) as error:
        reader.execute(ValidatedSQL(sql, 100))
    assert error.value.code == 'RETRIEVAL_TIMEOUT'
