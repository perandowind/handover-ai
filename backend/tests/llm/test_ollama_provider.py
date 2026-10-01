import asyncio
import json

import httpx
import pytest

from app.llm.errors import LLMProviderError, LLMResponseInvalidError
from app.llm.ollama_provider import OllamaLLMProvider
from app.schemas.llm import LLMOutput

pytestmark = pytest.mark.anyio


class Probe(LLMOutput):
    answer: str


def envelope(content='{"answer":"확인"}', **overrides):
    return {'message': {'role': 'assistant', 'content': content, 'thinking': 'not the answer'},
            'done': True, 'done_reason': 'stop', **overrides}


async def invoke(handler, *, schema=Probe, timeout=120):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaLLMProvider(client=client, base_url='http://ollama.test:11434/', timeout_seconds=timeout)
        return await provider.generate(model='test-model', system_prompt='system',
                                       user_prompt='user', response_schema=schema)


async def test_rest_contract_schema_and_timeout():
    requests = []
    async def handler(request):
        requests.append(request)
        assert request.method == 'POST'
        assert str(request.url) == 'http://ollama.test:11434/api/chat'
        assert request.headers['content-type'] == 'application/json'
        assert json.loads(request.content) == {
            'model': 'test-model', 'stream': False,
            'messages': [{'role': 'system', 'content': 'system'}, {'role': 'user', 'content': 'user'}],
            'format': Probe.model_json_schema(),
        }
        assert request.extensions['timeout'] == {'connect': 7, 'read': 7, 'write': 7, 'pool': 7}
        return httpx.Response(200, json=envelope())
    assert await invoke(handler, timeout=7) == '{"answer":"확인"}'
    assert len(requests) == 1


async def test_optional_schema_and_proxy_path():
    async def handler(request):
        assert str(request.url) == 'http://ollama.test/prefix/api/chat'
        assert 'format' not in json.loads(request.content)
        return httpx.Response(200, json=envelope('plain content'))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaLLMProvider(client=client, base_url='http://ollama.test/prefix/', timeout_seconds=1)
        assert await provider.generate(model='replacement-model', system_prompt='s', user_prompt='u') == 'plain content'
        assert not client.is_closed


@pytest.mark.parametrize('status,code,api_status', [
    (400, 'OLLAMA_REQUEST_FAILED', 502), (401, 'OLLAMA_REQUEST_FAILED', 502),
    (404, 'OLLAMA_MODEL_NOT_FOUND', 503), (429, 'OLLAMA_BUSY', 503),
    (500, 'OLLAMA_REQUEST_FAILED', 502), (503, 'OLLAMA_REQUEST_FAILED', 502),
    (307, 'OLLAMA_REQUEST_FAILED', 502),
])
async def test_http_errors_do_not_echo_remote_body_or_follow_redirect(status, code, api_status, caplog):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={'error': 'private upstream details'},
                              headers={'Location': 'https://external.test/collect'})
    with pytest.raises(LLMProviderError) as error:
        await invoke(handler)
    assert error.value.code == code and error.value.status_code == api_status
    assert error.value.detail == {'upstream_status': status}
    assert 'private upstream details' not in str(error.value) + caplog.text
    assert len(calls) == 1


@pytest.mark.parametrize('exception,code,status', [
    (httpx.ConnectError, 'OLLAMA_UNAVAILABLE', 503),
    (httpx.RemoteProtocolError, 'OLLAMA_UNAVAILABLE', 503),
    (httpx.ConnectTimeout, 'OLLAMA_TIMEOUT', 504),
    (httpx.ReadTimeout, 'OLLAMA_TIMEOUT', 504),
    (httpx.WriteTimeout, 'OLLAMA_TIMEOUT', 504),
    (httpx.PoolTimeout, 'OLLAMA_TIMEOUT', 504),
])
async def test_transport_errors_and_no_automatic_retry(exception, code, status):
    calls = []
    def handler(request):
        calls.append(request)
        raise exception('private transport context', request=request)
    with pytest.raises(LLMProviderError) as error:
        await invoke(handler)
    assert (error.value.code, error.value.status_code) == (code, status)
    assert 'private transport context' not in str(error.value)
    assert len(calls) == 1


async def test_total_deadline_bounds_slow_transport():
    async def handler(request):
        await asyncio.Event().wait()
    with pytest.raises(LLMProviderError) as error:
        await invoke(handler, timeout=.01)
    assert error.value.code == 'OLLAMA_TIMEOUT'


async def test_cancellation_is_not_converted_to_error_or_retried():
    started = asyncio.Event()
    calls = []
    async def handler(request):
        calls.append(request)
        started.set()
        await asyncio.Event().wait()
    pending = asyncio.create_task(invoke(handler))
    await started.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert len(calls) == 1


@pytest.mark.parametrize('body', [
    {}, [], None,
    {'done': True},
    envelope(message={'role': 'user', 'content': '{}'}),
    envelope(message={'role': 'assistant', 'content': None}),
    envelope(message={'role': 'assistant', 'content': {}}),
    envelope(message={'role': 'assistant', 'content': ''}),
    envelope(message={'role': 'assistant', 'content': '   ', 'thinking': '{"answer":"hidden"}'}),
    envelope(done=False), envelope(done='true'), envelope(done=1),
    envelope(done_reason='length'),
])
async def test_invalid_ollama_envelope(body):
    with pytest.raises(LLMResponseInvalidError) as error:
        await invoke(lambda request: httpx.Response(200, json=body))
    assert error.value.detail['stage'] == 'envelope'


async def test_invalid_http_json():
    with pytest.raises(LLMResponseInvalidError):
        await invoke(lambda request: httpx.Response(200, content=b'<html>server error</html>'))


async def test_error_inside_success_status_is_failure():
    with pytest.raises(LLMProviderError) as error:
        await invoke(lambda request: httpx.Response(200, json={'error': 'private model error'}))
    assert error.value.code == 'OLLAMA_REQUEST_FAILED'
    assert 'private model error' not in str(error.value)
