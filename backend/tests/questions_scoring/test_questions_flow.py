import copy
import json

import pytest
from sqlalchemy import func, select

from app.models import Question
from app.retrieval.context import ContextBuilder
from app.services.question_context import build_question_context
from app.schemas.llm import QuestionGenerationResult
from app.core.exceptions import AppError


def sql(statement='SELECT id AS source_section_id, content FROM document_sections ORDER BY id'):
    return json.dumps({'sql': statement, 'reason': '관련 섹션 조회'})


def count_saved(client):
    with client.app.state.session_factory() as session:
        return session.scalar(select(func.count()).select_from(Question))


def test_real_retrieval_question_generation_persistence_and_answer_boundary(api_factory, provider_factory, question_payload):
    provider = provider_factory(sql(), json.dumps(question_payload))
    client = api_factory(provider)
    response = client.post('/api/questions/generate', json={'document_ids': [1], 'count': 1, 'prompt': '백업 문제'})
    assert response.status_code == 201, response.text
    result = response.json()[0]
    assert result['document_id'] == result['section_id'] == 1
    assert result['choices'] == ['매일', '매월']
    assert 'correct_answer' not in result and 'explanation' not in result
    assert client.get('/api/questions').json() == [result]
    assert client.get('/api/questions/1').json() == result
    assert client.get('/api/questions/1/answer').json() == {'correct_answer': '1', 'explanation': question_payload['questions'][0]['explanation']}
    assert count_saved(client) == 1
    assert [call['model'] for call in provider.calls] == ['sql-test', 'question-test']
    payload = json.loads(provider.calls[1]['user_prompt'])
    assert payload['allowed_source_section_ids'] == [1]
    assert '매일 확인' in payload['context'] and '비공개' not in payload['context']


def test_short_answer_generation(api_factory, provider_factory, question_payload):
    item = question_payload['questions'][0]
    item.update(question_type='short_answer', choices=None, correct_answer='PostgreSQL', question='시스템 이름은?')
    client = api_factory(provider_factory(sql(), json.dumps(question_payload)))
    response = client.post('/api/questions/generate', json={'count': 1, 'question_type': 'short_answer', 'document_ids': [1]})
    assert response.status_code == 201 and response.json()[0]['choices'] is None
    assert client.get('/api/questions/1/answer').json()['correct_answer'] == 'PostgreSQL'


@pytest.mark.parametrize('case', ['count', 'type', 'source', 'source_null', 'answer', 'choices', 'duplicate_choices', 'duplicate_question', 'json'])
def test_invalid_generation_gets_one_retry_then_no_partial_save(api_factory, provider_factory, question_payload, case):
    item = question_payload['questions'][0]
    count = 1
    if case == 'count': count = 2
    if case == 'type': item.update(question_type='short_answer', choices=None)
    if case == 'source': item['source_section_id'] = 2
    if case == 'source_null': item['source_section_id'] = None
    if case == 'answer': item['correct_answer'] = '3'
    if case == 'choices': item['choices'] = ['매일']
    if case == 'duplicate_choices': item['choices'] = ['매일', ' 매일 ']
    if case == 'duplicate_question':
        question_payload['questions'].append(copy.deepcopy(item)); count = 2
    invalid = 'bad JSON' if case == 'json' else json.dumps(question_payload)
    provider = provider_factory(sql(), invalid, invalid)
    client = api_factory(provider)
    response = client.post('/api/questions/generate', json={'document_ids': [1], 'count': count})
    assert response.status_code == 502 and response.json()['code'] == 'QUESTION_GENERATION_FAILED'
    assert count_saved(client) == 0
    assert [call['model'] for call in provider.calls] == ['sql-test', 'question-test', 'question-test']


def test_correction_retry_saves_exactly_once(api_factory, provider_factory, question_payload):
    provider = provider_factory(sql(), '{"questions":[]}', json.dumps(question_payload))
    client = api_factory(provider)
    assert client.post('/api/questions/generate', json={'count': 1, 'document_ids': [1]}).status_code == 201
    assert count_saved(client) == 1
    retry = json.loads(provider.calls[-1]['user_prompt'])
    assert retry['previous_validation_error'] == 'INVALID_JSON_OR_SCHEMA'


@pytest.mark.parametrize('statement', [
    'SELECT id AS source_section_id FROM document_sections WHERE id=999',
    'SELECT 999 AS source_section_id FROM document_sections',
    'SELECT 2 AS source_section_id FROM document_sections',
    'SELECT 3 AS source_section_id FROM document_sections',
    'SELECT content FROM document_sections',
])
def test_empty_invalid_or_out_of_scope_sources_never_call_question_model(api_factory, provider_factory, statement):
    provider = provider_factory(sql(statement))
    client = api_factory(provider)
    response = client.post('/api/questions/generate', json={'count': 1, 'document_ids': [1]})
    assert response.status_code == 422 and response.json()['code'] == 'QUESTION_CONTEXT_EMPTY'
    assert len(provider.calls) == 1 and count_saved(client) == 0


def test_canonical_content_replaces_sql_literal_evidence(api_factory, provider_factory, question_payload):
    provider = provider_factory(sql("SELECT id AS source_section_id, 'FAKE_SOURCE' AS content FROM document_sections"), json.dumps(question_payload))
    client = api_factory(provider)
    assert client.post('/api/questions/generate', json={'count': 1, 'document_ids': [1]}).status_code == 201
    context = json.loads(provider.calls[-1]['user_prompt'])['context']
    assert 'FAKE_SOURCE' not in context and '매일 확인' in context


@pytest.mark.parametrize('ids,status', [([999], 404), ([3], 409)])
def test_missing_or_unready_selection(api_factory, provider_factory, ids, status):
    provider = provider_factory()
    client = api_factory(provider)
    assert client.post('/api/questions/generate', json={'document_ids': ids}).status_code == status
    assert not provider.calls


def test_sql_validation_failure_stops_generation(api_factory, provider_factory):
    provider = provider_factory(sql('DROP TABLE questions'), sql('DROP TABLE questions'))
    client = api_factory(provider)
    response = client.post('/api/questions/generate', json={'count': 1})
    assert response.status_code == 502 and response.json()['code'] == 'SQL_GENERATION_FAILED'
    assert count_saved(client) == 0


@pytest.mark.parametrize('body', [{'count': 0}, {'count': 21}, {'count': True}, {'count': '2'},
                                   {'question_type': 'essay'}, {'document_ids': [1, 1]}, {'prompt': ' '}])
def test_bad_question_requests(api_factory, provider_factory, body):
    provider = provider_factory()
    client = api_factory(provider)
    assert client.post('/api/questions/generate', json=body).status_code == 422
    assert not provider.calls


def test_context_limits_and_only_visible_source_ids():
    rows = [{'source_section_id': 1, 'document_id': 1, 'section_title': '업무', 'content': '매일 확인합니다. ' * 500},
            {'source_section_id': 2, 'document_id': 2, 'section_title': '다른 업무', 'content': '숨겨진 내용'}]
    context = build_question_context(rows, ContextBuilder(100, 180))
    assert len(context.text) <= 180 and context.truncated
    assert context.source_documents == {1: 1} and '숨겨진 내용' not in context.text
    tiny = build_question_context(rows, ContextBuilder(100, 1))
    assert tiny.text == '' and tiny.source_documents == {}


def test_save_batch_rolls_back_if_later_source_disappeared(api_factory, provider_factory, question_payload):
    client = api_factory(provider_factory())
    second = copy.deepcopy(question_payload['questions'][0])
    second.update(question='두 번째 문제', source_section_id=999)
    question_payload['questions'].append(second)
    with pytest.raises(AppError):
        client.app.state.question_repository.save_questions(QuestionGenerationResult.model_validate(question_payload), {1: 1, 999: 1})
    assert count_saved(client) == 0


def test_unknown_question_and_pagination(api_factory, provider_factory):
    client = api_factory(provider_factory())
    assert client.get('/api/questions?offset=100&limit=20').json() == []
    assert client.get('/api/questions?limit=101').status_code == 422
    assert client.get('/api/questions/999').status_code == 404
    assert client.get('/api/questions/999/answer').status_code == 404
