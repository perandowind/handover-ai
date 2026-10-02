import json
from dataclasses import dataclass

_LABELS = {
    'source_section_id': '원천 섹션 ID',
    'id': 'ID', 'document_id': '문서 ID', 'section_id': '섹션 ID',
    'title': '문서 제목', 'document_type': '문서 유형', 'department': '부서',
    'section_type': '섹션 유형', 'section_title': '섹션 제목', 'content': '내용',
    'sequence': '순서', 'source_page': '원본 페이지', 'category': '카테고리',
    'task_name': '업무명', 'description': '설명', 'procedure': '절차',
    'precaution': '주의사항', 'importance': '중요도', 'frequency': '주기',
    'related_system': '관련 시스템', 'contact_info': '연락처',
}


@dataclass(frozen=True)
class BuiltContext:
    text: str
    truncated: bool


class ContextBuilder:
    def __init__(self, max_rows: int, max_chars: int):
        if max_rows < 1 or max_chars < 1:
            raise ValueError('Context limits must be positive')
        self.max_rows = max_rows
        self.max_chars = max_chars

    def build(self, rows: list[dict]) -> BuiltContext:
        # Preserve SQL relevance/order. Quoted, escaped values are evidence, not
        # instructions; later generation tasks must retain that trust boundary.
        blocks = []
        for index, row in enumerate(rows[:self.max_rows], 1):
            lines = [f'[검색 결과 {index}]']
            for key, value in row.items():
                if value is not None:
                    label = _LABELS.get(key, json.dumps(key, ensure_ascii=False))
                    lines.append(f'{label}: {json.dumps(value, ensure_ascii=False)}')
            blocks.append('\n'.join(lines))
        text = '\n\n'.join(blocks)
        truncated = len(rows) > self.max_rows or len(text) > self.max_chars
        if len(text) > self.max_chars:
            marker = '\n[Context 생략]'
            text = text[:max(0, self.max_chars - len(marker))] + marker[:self.max_chars]
        return BuiltContext(text=text, truncated=truncated)
