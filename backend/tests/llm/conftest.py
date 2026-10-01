import httpx
import pytest


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture(autouse=True)
def no_real_http(monkeypatch):
    async def reject_network(*args, **kwargs):
        raise AssertionError('LLM tests must use MockTransport or an injected provider')
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', reject_network)
