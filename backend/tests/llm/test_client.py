import asyncio
import logging

import pytest

from app.core.config import Settings
from app.llm.client import StructuredLLMClient
from app.llm.errors import LLMProviderError, LLMResponseInvalidError
from app.llm.provider import LLMProvider
from app.llm.tasks import configure_tasks
from app.llm.tasks.base import TaskDefinition
from app.schemas.llm import LLMOutput

pytestmark = pytest.mark.anyio


class Probe(LLMOutput):
    answer: str


class SequenceProvider(LLMProvider):
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response


def probe_task(retries=1):
    return TaskDefinition('probe', 'configured-model', 'test system', Probe, retries)


async def test_mock_provider_returns_typed_result_and_receives_schema():
    provider = SequenceProvider(['{"answer":"검증 완료"}'])
    result = await StructuredLLMClient(provider).generate(task=probe_task(), user_prompt='test input')
    assert result == Probe(answer='검증 완료')
    call = provider.calls[0]
    assert call['model'] == 'configured-model' and call['response_schema'] is Probe
    assert call['user_prompt'] == 'test input' and 'JSON Schema:' in call['system_prompt']
    assert len(provider.calls) == 1


@pytest.mark.parametrize('first_response', ['invalid JSON', '{"answer":123}', LLMResponseInvalidError('envelope')])
async def test_invalid_output_has_one_correction_retry(first_response):
    provider = SequenceProvider([first_response, '{"answer":"fixed"}'])
    result = await StructuredLLMClient(provider).generate(task=probe_task(), user_prompt='request')
    assert result.answer == 'fixed' and len(provider.calls) == 2
    assert provider.calls[0]['user_prompt'] == provider.calls[1]['user_prompt']
    assert '검증에 실패' in provider.calls[1]['system_prompt']
    assert 'invalid JSON' not in provider.calls[1]['system_prompt']


async def test_retry_exhausted_never_returns_invalid_result():
    provider = SequenceProvider(['invalid', '{"wrong_field":"private response"}'])
    with pytest.raises(LLMResponseInvalidError):
        await StructuredLLMClient(provider).generate(task=probe_task(), user_prompt='request')
    assert len(provider.calls) == 2


@pytest.mark.parametrize('code', ['OLLAMA_UNAVAILABLE', 'OLLAMA_TIMEOUT', 'OLLAMA_MODEL_NOT_FOUND', 'OLLAMA_REQUEST_FAILED'])
async def test_transport_or_model_failure_is_not_retried(code):
    provider = SequenceProvider([LLMProviderError(code, 'failed', 503)])
    with pytest.raises(LLMProviderError) as error:
        await StructuredLLMClient(provider).generate(task=probe_task(), user_prompt='request')
    assert error.value.code == code and len(provider.calls) == 1


@pytest.mark.parametrize('response', ['bad json', '{"score":101,"is_correct":true,"reason":"invalid"}', LLMProviderError('OLLAMA_TIMEOUT', 'timeout', 504)])
async def test_scoring_propagates_failure_once_for_future_python_fallback(response):
    provider = SequenceProvider([response])
    task = configure_tasks(Settings(_env_file=None))['scoring']
    with pytest.raises((LLMResponseInvalidError, LLMProviderError)):
        await StructuredLLMClient(provider).generate(task=task, user_prompt='request')
    assert len(provider.calls) == 1


async def test_valid_scoring_result_is_not_recomputed():
    provider = SequenceProvider(['{"score":73.5,"is_correct":null,"reason":"부분 정답"}'])
    result = await StructuredLLMClient(provider).generate(
        task=configure_tasks(Settings(_env_file=None))['scoring'], user_prompt='request')
    assert result.score == 73.5 and len(provider.calls) == 1


async def test_cancellation_propagates():
    provider = SequenceProvider([asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        await StructuredLLMClient(provider).generate(task=probe_task(), user_prompt='request')
    assert len(provider.calls) == 1


async def test_logging_does_not_expose_private_input_or_output(caplog):
    caplog.set_level(logging.INFO)
    provider = SequenceProvider(['{"unknown":"private-response"}', '{"answer":"ok"}'])
    await StructuredLLMClient(provider).generate(task=probe_task(), user_prompt='private-document-body')
    assert 'task=probe' in caplog.text and 'stage=schema' in caplog.text
    assert 'private-response' not in caplog.text and 'private-document-body' not in caplog.text


async def test_task_model_settings_and_policy_are_independent(monkeypatch):
    for env, model in [('SQL_MODEL', 'sql-test'), ('DOCUMENT_MODEL', 'document-test'),
                       ('QUESTION_MODEL', 'question-test'), ('SCORING_MODEL', 'scoring-test')]:
        monkeypatch.setenv(env, model)
    tasks = configure_tasks(Settings(_env_file=None))
    assert {name: task.model for name, task in tasks.items()} == {
        'sql_generation': 'sql-test', 'document_generation': 'document-test',
        'question_generation': 'question-test', 'scoring': 'scoring-test',
    }
    assert {name: task.validation_retries for name, task in tasks.items()} == {
        'sql_generation': 1, 'document_generation': 1, 'question_generation': 1, 'scoring': 0,
    }
    assert len({task.system_prompt for task in tasks.values()}) == 4
    assert len({task.response_schema for task in tasks.values()}) == 4


async def test_default_models_and_boundary_policies():
    tasks = configure_tasks(Settings(_env_file=None))
    assert {task.model for task in tasks.values()} == {'qwen3.5:4b'}
    assert 'SQL Validator' in tasks['sql_generation'].system_prompt
    assert '관련 정보 없음' in tasks['document_generation'].system_prompt
    assert 'Context 밖의 사실' in tasks['question_generation'].system_prompt
    assert '0~100' in tasks['scoring'].system_prompt


async def test_interface_is_abstract_and_retry_budget_is_bounded():
    with pytest.raises(TypeError):
        LLMProvider()
    with pytest.raises(ValueError):
        probe_task(retries=2)
