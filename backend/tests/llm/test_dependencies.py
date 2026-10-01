import httpx
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.llm.client import StructuredLLMClient
from app.llm.dependencies import get_llm_client, get_llm_provider, managed_provider
from app.llm.errors import LLMProviderError
from app.llm.provider import LLMProvider
from app.llm.tasks.base import TaskDefinition
from app.main import create_app
from app.schemas.llm import LLMOutput


class FakeProvider(LLMProvider):
    def __init__(self, error=None):
        self.calls = 0
        self.error = error

    async def generate(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return '{"message":"ok"}'


class Probe(LLMOutput):
    message: str


def settings(tmp_path):
    return Settings(_env_file=None, database_url=f'sqlite:///{tmp_path / "test.db"}',
                    ollama_base_url='http://ollama.invalid:11434')


def test_application_starts_without_ollama_and_excludes_future_routes(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        assert client.get('/api/health').json() == {'status': 'ok'}
        assert isinstance(app.state.llm_provider, LLMProvider)
        assert set(app.state.llm_tasks) == {'sql_generation', 'document_generation', 'question_generation', 'scoring'}
        paths = client.get('/openapi.json').json()['paths']
        assert '/api/documents/upload' in paths
        assert '/api/generation/handover' in paths
        assert '/api/generation/handover/pdf' in paths
        assert not any(path.startswith(('/api/questions', '/api/scoring')) for path in paths)


def test_fastapi_dependency_injection_with_mock_provider(tmp_path):
    provider = FakeProvider()
    app = create_app(settings(tmp_path), llm_provider=provider)
    @app.get('/test/llm-probe')
    async def probe(client: StructuredLLMClient = Depends(get_llm_client),
                    injected: LLMProvider = Depends(get_llm_provider)):
        assert injected is provider
        return await client.generate(task=TaskDefinition('probe', 'test-model', 's', Probe), user_prompt='test')
    with TestClient(app) as client:
        assert provider.calls == 0
        assert client.get('/test/llm-probe').json() == {'message': 'ok'}
        assert provider.calls == 1
    assert provider.calls == 1


def test_llm_errors_use_existing_common_error_response(tmp_path):
    provider = FakeProvider(LLMProviderError('OLLAMA_UNAVAILABLE', 'LLM 서버에 연결할 수 없습니다.', 503))
    app = create_app(settings(tmp_path), llm_provider=provider)
    @app.get('/test/llm-error')
    async def error(client: StructuredLLMClient = Depends(get_llm_client)):
        return await client.generate(task=TaskDefinition('probe', 'test-model', 's', Probe), user_prompt='test')
    with TestClient(app) as client:
        response = client.get('/test/llm-error')
        assert response.status_code == 503
        assert response.json() == {'code': 'OLLAMA_UNAVAILABLE', 'message': 'LLM 서버에 연결할 수 없습니다.', 'detail': {}}


@pytest.mark.anyio
async def test_owned_http_client_closed_on_normal_or_failed_exit(monkeypatch, tmp_path):
    instances = []
    original_client = httpx.AsyncClient
    def factory(**kwargs):
        assert kwargs['trust_env'] is False
        client = original_client(**kwargs)
        instances.append(client)
        return client
    monkeypatch.setattr(httpx, 'AsyncClient', factory)
    async with managed_provider(settings(tmp_path)):
        assert not instances[-1].is_closed
    assert instances[-1].is_closed
    with pytest.raises(RuntimeError):
        async with managed_provider(settings(tmp_path)):
            raise RuntimeError('test failure')
    assert len(instances) == 2 and all(client.is_closed for client in instances)


@pytest.mark.anyio
async def test_injected_provider_does_not_construct_http_client(monkeypatch, tmp_path):
    def forbidden(**kwargs):
        raise AssertionError('Injected provider must not create a real HTTP client')
    monkeypatch.setattr(httpx, 'AsyncClient', forbidden)
    provider = FakeProvider()
    async with managed_provider(settings(tmp_path), provider) as actual:
        assert actual is provider
