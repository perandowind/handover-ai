import httpx
import pytest


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture(autouse=True)
def forbid_live_llm(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError('Retrieval tests must not access the network')
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
