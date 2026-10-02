from dataclasses import dataclass

from app.retrieval.context import ContextBuilder


@dataclass(frozen=True)
class QuestionContext:
    text: str
    source_documents: dict[int, int]
    truncated: bool


def build_question_context(rows: list[dict], builder: ContextBuilder) -> QuestionContext:
    """Keep IDs only for source records actually included in bounded context."""
    included = []
    truncated = False
    for row in rows[:builder.max_rows]:
        if not builder.build(included + [row]).truncated:
            included.append(row)
            continue
        # Keep a useful prefix of a large section without truncating its ID/header.
        low, high = 0, len(row['content'])
        while low < high:
            middle = (low + high + 1) // 2
            candidate = {**row, 'content': row['content'][:middle]}
            if builder.build(included + [candidate]).truncated:
                high = middle - 1
            else:
                low = middle
        if row['content'][:low].strip():
            included.append({**row, 'content': row['content'][:low]})
        truncated = True
        break
    return QuestionContext(
        builder.build(included).text,
        {row['source_section_id']: row['document_id'] for row in included},
        truncated or len(included) < len(rows),
    )
