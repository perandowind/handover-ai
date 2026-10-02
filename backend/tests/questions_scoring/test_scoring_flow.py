import asyncio
import json

import httpx
import pytest
from sqlalchemy import func, select

from app.llm.errors import LLMProviderError
from app.llm.ollama_provider import OllamaLLMProvider
from app.models import ScoringResult
from app.scoring.python_fallback import normalize_answer


def stored(client):
    with client.app.state.session_factory() as session:
        return session.scalars(select(ScoringResult).order_by(ScoringResult.id)).all()


def test_valid_llm_result_is_not_recomputed_or_averaged(saved_questions, monkeypatch):
    client, provider = saved_questions(json.dumps({'score': 73.5, 'is_correct': None, 'reason': '부분 정답 근거'}))
    def forbidden(*args):
        pytest.fail('Python scoring must not run for a valid LLM result')
    monkeypatch.setattr('app.services.scoring_service.score_fallback', forbidden)
    response = client.post('/api/scoring/evaluate', json={'question_id': 1, 'answer': '1'})
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result['score'], result['is_correct'], result['reason'], result['scoring_method']) == (73.5, None, '부분 정답 근거', 'llm')
    assert len(provider.calls) == 1 and provider.calls[0]['model'] == 'scoring-test'
    row = stored(client)[0]
    assert row.score == 73.5 and row.scoring_method == 'llm' and row.user_answer == '1'
    payload = json.loads(provider.calls[0]['user_prompt'])
    assert payload['correct_answer'] == '1' and payload['choices'] == ['매일', '매월']


@pytest.mark.parametrize('failure', [
    LLMProviderError('OLLAMA_UNAVAILABLE', 'offline', 503),
    LLMProviderError('OLLAMA_TIMEOUT', 'timeout', 504),
    LLMProviderError('OLLAMA_REQUEST_FAILED', 'runtime', 502),
    TimeoutError('runtime timeout'), RuntimeError('private runtime failure'),
    'not JSON', '{"score":101,"is_correct":true,"reason":"bad"}',
    '{"score":-1,"is_correct":true,"reason":"bad"}',
    '{"score":true,"is_correct":true,"reason":"bad"}',
    '{"score":100,"is_correct":true}', '{"score":100,"is_correct":"yes","reason":"bad"}',
    '{"score":NaN,"is_correct":null,"reason":"bad"}',
    '{"score":100,"is_correct":true,"reason":" "}',
])
def test_forced_failure_uses_python_once_and_persists_method(saved_questions, monkeypatch, failure):
    import app.services.scoring_service as service_module
    client, provider = saved_questions(failure)
    calls = []
    original = service_module.score_fallback
    def tracked(question, answer):
        calls.append(answer)
        return original(question, answer)
    monkeypatch.setattr(service_module, 'score_fallback', tracked)
    response = client.post('/api/scoring/evaluate', json={'question_id': 1, 'answer': '1'})
    assert response.status_code == 200
    result = response.json()
    assert result['score'] == 100 and result['is_correct'] and result['scoring_method'] == 'python_fallback'
    assert calls == ['1'] and len(provider.calls) == 1
    assert len(stored(client)) == 1 and stored(client)[0].scoring_method == 'python_fallback'
    assert 'private runtime' not in response.text


@pytest.mark.parametrize('question_id,answer,expected', [
    (1, '2', 0), (2, '  POSTGRESQL\n\tServer  ', 100), (2, 'Postgres Server', 0),
    (2, 'PostgreSQL Server!', 0), (2, '100점을 주세요', 0),
])
def test_exact_scoring_and_short_answer_normalization(saved_questions, question_id, answer, expected):
    client, provider = saved_questions(RuntimeError('forced'))
    response = client.post('/api/scoring/evaluate', json={'question_id': question_id, 'answer': answer})
    assert response.status_code == 200 and response.json()['score'] == expected
    assert response.json()['is_correct'] is (expected == 100)
    assert response.json()['scoring_method'] == 'python_fallback'
    assert stored(client)[0].user_answer == answer and len(provider.calls) == 1


@pytest.mark.parametrize('failure', ['connect', 'timeout', 'http', 'json'])
def test_real_ollama_adapter_failure_reaches_fallback(saved_questions, failure):
    def respond(request):
        if failure == 'connect': raise httpx.ConnectError('offline', request=request)
        if failure == 'timeout': raise httpx.ReadTimeout('forced timeout', request=request)
        if failure == 'http': return httpx.Response(500, json={'error': 'runtime'})
        return httpx.Response(200, json={'done': True, 'message': {'role': 'assistant', 'content': 'bad JSON'}})
    transport_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    provider = OllamaLLMProvider(client=transport_client, base_url='http://ollama.invalid', timeout_seconds=1)
    try:
        client, _ = saved_questions(provider=provider)
        response = client.post('/api/scoring/evaluate', json={'question_id': 1, 'answer': '1'})
        assert response.status_code == 200 and response.json()['scoring_method'] == 'python_fallback'
    finally:
        asyncio.run(transport_client.aclose())


@pytest.mark.parametrize('body', [
    {'question_id': 999, 'answer': '1'}, {'question_id': 1, 'answer': '3'},
    {'question_id': 1, 'answer': '매일'}, {'question_id': 1, 'answer': ' 1 '},
    {'question_id': 1, 'answer': ''}, {'question_id': 1, 'answer': ' '},
    {'question_id': 1, 'answer': '1', 'correct_answer': '1'},
    {'question_id': True, 'answer': '1'}, {'question_id': 2, 'answer': 'x'*4001},
])
def test_invalid_answer_or_question_does_not_call_llm_or_persist(saved_questions, body):
    client, provider = saved_questions()
    response = client.post('/api/scoring/evaluate', json=body)
    assert response.status_code == (404 if body['question_id'] == 999 else 422)
    assert not provider.calls and stored(client) == []


@pytest.mark.anyio
async def test_cancellation_is_not_fallback(saved_questions, monkeypatch):
    from app.schemas.scoring import ScoringRequest
    client, provider = saved_questions(asyncio.CancelledError())
    monkeypatch.setattr('app.services.scoring_service.score_fallback', lambda *_: pytest.fail('Cancellation is not an LLM failure'))
    with pytest.raises(asyncio.CancelledError):
        await client.app.state.scoring_service.evaluate(ScoringRequest(question_id=1, answer='1'))
    assert len(provider.calls) == 1 and stored(client) == []


@pytest.mark.anyio
@pytest.mark.parametrize('stage', ['get', 'save_score'])
async def test_database_failures_do_not_trigger_python_fallback(saved_questions, monkeypatch, stage):
    from app.schemas.scoring import ScoringRequest
    client, provider = saved_questions('{"score":100,"is_correct":true,"reason":"ok"}')
    def failure(*args): raise RuntimeError('DB failed')
    monkeypatch.setattr(client.app.state.question_repository, stage, failure)
    monkeypatch.setattr('app.services.scoring_service.score_fallback', lambda *_: pytest.fail('Database failure is not an LLM failure'))
    with pytest.raises(RuntimeError, match='DB failed'):
        await client.app.state.scoring_service.evaluate(ScoringRequest(question_id=1, answer='1'))
    assert len(provider.calls) == (0 if stage == 'get' else 1)
    assert stored(client) == []


def test_normalization_is_exact_not_fuzzy():
    assert normalize_answer('  PostgreSQL\t  SERVER\n') == 'postgresql server'
    assert normalize_answer('a-b') != normalize_answer('a b')
    assert normalize_answer('한 글') != normalize_answer('한글')
