import json

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, Settings, get_settings
from app.db.session import create_db_engine
from app.llm.provider import LLMProvider
from app.main import create_app
from app.models import Document, DocumentSection, Question


class MockProvider(LLMProvider):
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture(autouse=True)
def no_live_http(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail('Only mocked LLM calls are allowed')
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)


@pytest.fixture
def provider_factory():
    return MockProvider


@pytest.fixture
def question_payload():
    return {'questions': [{'question_type': 'multiple_choice', 'question': '백업 확인 주기는?',
                           'choices': ['매일', '매월'], 'correct_answer': '1',
                           'explanation': '원문에 매일 확인한다고 명시되어 있습니다.', 'source_section_id': 1}]}


@pytest.fixture
def api_factory(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "phase7.db"}'
    monkeypatch.setenv('DATABASE_URL', url)
    get_settings.cache_clear()
    command.upgrade(Config(str(BACKEND_DIR/'alembic.ini')), 'head')
    engine = create_db_engine(url)
    with Session(engine) as session:
        for id in range(1, 4):
            session.add(Document(id=id, title=f'문서 {id}', document_type='handover',
                                 source_filename=f'{id}.pdf', source_path=f'uploads/{id}.pdf',
                                 ocr_status='completed' if id < 3 else 'pending',
                                 parse_status='completed' if id < 3 else 'pending'))
        session.flush()
        for id, content in [(1, '백업은 매일 확인합니다. 시스템 이름은 PostgreSQL입니다.'),
                            (2, '선택하지 않은 문서의 비공개 내용'), (3, '처리 중 문서')]:
            session.add(DocumentSection(id=id, document_id=id, section_type='procedures',
                                        section_title='업무 절차', content=content, sequence=1, source_page=1))
        session.commit()
    engine.dispose()
    clients = []
    def factory(provider, **kwargs):
        settings = Settings(_env_file=None, database_url=url, sql_model='sql-test',
                            question_model='question-test', scoring_model='scoring-test', **kwargs)
        client = TestClient(create_app(settings, llm_provider=provider))
        client.__enter__()
        clients.append(client)
        return client
    yield factory
    for client in reversed(clients):
        client.__exit__(None, None, None)
    get_settings.cache_clear()


@pytest.fixture
def saved_questions(api_factory, provider_factory):
    def factory(*responses, provider=None):
        provider = provider or provider_factory(*responses)
        client = api_factory(provider)
        with client.app.state.session_factory() as session:
            session.add_all([
                Question(id=1, document_id=1, section_id=1, question_type='multiple_choice',
                         question_text='백업 주기는?', choices_json=json.dumps(['매일', '매월']),
                         correct_answer='1', explanation='매일 확인'),
                Question(id=2, document_id=1, section_id=1, question_type='short_answer',
                         question_text='시스템 이름은?', correct_answer='PostgreSQL Server', explanation='원문 시스템'),
            ])
            session.commit()
        return client, provider
    return factory
