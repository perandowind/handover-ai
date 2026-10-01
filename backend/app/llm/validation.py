import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.llm.errors import LLMResponseInvalidError

OutputT = TypeVar('OutputT', bound=BaseModel)


def _reject_constant(value: str):
    raise ValueError('Non-finite JSON number')


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def parse_and_validate(raw: str, response_schema: type[OutputT]) -> OutputT:
    """Accept exactly one JSON object, then apply strict Pydantic validation.

    No code fence stripping, prose extraction, Python literal evaluation, or
    output repair. Invalid output must remain a failure, never an executable value.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise LLMResponseInvalidError('json')
    try:
        data = json.loads(raw, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError):
        raise LLMResponseInvalidError('json') from None
    if not isinstance(data, dict):
        raise LLMResponseInvalidError('json')
    try:
        return response_schema.model_validate(data, strict=True)
    except ValidationError as exc:
        # Do not expose input values, dynamic field names, or validation context.
        raise LLMResponseInvalidError('schema', error_count=exc.error_count()) from None
