import json

import pytest

from app.core.handover import HANDOVER_OUTLINE
from app.llm.errors import LLMResponseInvalidError
from app.llm.validation import parse_and_validate
from app.schemas.llm import (
    GeneratedDocument, LLMScoringResult, QuestionGenerationResult, SQLGenerationOutput,
)


def test_valid_json_and_pydantic_result():
    result = parse_and_validate(' {"score": 100, "is_correct": true, "reason": "정답"} ', LLMScoringResult)
    assert isinstance(result, LLMScoringResult)
    assert result.score == 100 and result.is_correct is True


@pytest.mark.parametrize('raw', [
    '', ' ', 'not JSON', '```json\n{"score":100}\n```',
    'Result: {"score":100}', '<think>reasoning</think>{"score":100}',
    '{}{}', '[]', 'null', '42', '"text"', '{"score": NaN}', '{"score": Infinity}',
    '{"score": 1, "score": 100}', '{"nested":{"key":1,"key":2}}',
    '__import__("os").system("echo bad")',
])
def test_invalid_json_is_rejected_without_repair(raw):
    with pytest.raises(LLMResponseInvalidError) as error:
        parse_and_validate(raw, LLMScoringResult)
    assert error.value.detail['stage'] == 'json'


@pytest.mark.parametrize('changes', [
    {'score': -1}, {'score': 101}, {'score': '100'}, {'score': True},
    {'score': None}, {'is_correct': 'true'}, {'is_correct': 1},
    {'reason': ''}, {'reason': '  '}, {'extra': 'private text'},
])
def test_invalid_scoring_output(changes):
    body = {'score': 90, 'is_correct': None, 'reason': '부분 정답', **changes}
    with pytest.raises(LLMResponseInvalidError) as error:
        parse_and_validate(json.dumps(body), LLMScoringResult)
    assert error.value.detail['stage'] == 'schema'
    assert 'private text' not in str(error.value) + str(error.value.detail)


@pytest.mark.parametrize('missing', ['score', 'is_correct', 'reason'])
def test_required_keys_even_when_nullable(missing):
    body = {'score': 0, 'is_correct': None, 'reason': '판정 불가'}
    del body[missing]
    with pytest.raises(LLMResponseInvalidError):
        parse_and_validate(json.dumps(body), LLMScoringResult)


def test_overflow_to_infinity_is_rejected():
    with pytest.raises(LLMResponseInvalidError):
        parse_and_validate('{"score":1e999,"is_correct":null,"reason":"overflow"}', LLMScoringResult)


def test_nested_document_contract():
    result = parse_and_validate(json.dumps({'title': '인수인계서', 'sections': [
        {'section_type': key, 'title': title, 'content': '관련 정보 없음'}
        for key, title in HANDOVER_OUTLINE
    ]}), GeneratedDocument)
    assert result.sections[0].content == '관련 정보 없음'
    with pytest.raises(LLMResponseInvalidError):
        parse_and_validate('{"title":"test","sections":[{"title":"missing keys"}]}', GeneratedDocument)


def test_question_contract_and_type():
    item = {'question_type': 'multiple_choice', 'question': '질문', 'choices': ['가', '나'],
            'correct_answer': '1', 'explanation': '근거', 'source_section_id': 1}
    result = parse_and_validate(json.dumps({'questions': [item]}), QuestionGenerationResult)
    assert result.questions[0].source_section_id == 1
    item['question_type'] = 'unsupported'
    with pytest.raises(LLMResponseInvalidError):
        parse_and_validate(json.dumps({'questions': [item]}), QuestionGenerationResult)


def test_sql_contract_is_not_a_sql_validator():
    # It is intentionally just text. Phase 4 MUST validate it before any execution.
    result = parse_and_validate('{"sql":"DROP TABLE documents;", "reason":"untrusted"}', SQLGenerationOutput)
    assert result.sql == 'DROP TABLE documents;'
    with pytest.raises(LLMResponseInvalidError):
        parse_and_validate('{"sql":"SELECT 1"}', SQLGenerationOutput)
