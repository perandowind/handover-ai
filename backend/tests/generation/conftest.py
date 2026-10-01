import httpx
import pytest


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture(autouse=True)
def forbid_live_llm(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError('Generation tests must not access the network')
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)


@pytest.fixture
def document_body():
    from app.core.handover import HANDOVER_OUTLINE
    return {'title': 'DB 운영 인수인계서', 'sections': [
        {'section_type': key, 'title': title, 'content': '관련 정보 없음'}
        for key, title in HANDOVER_OUTLINE
    ]}
