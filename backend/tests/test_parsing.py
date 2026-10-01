from app.models import DocumentSection
from app.parsing.item_mapper import map_handover_items
from app.parsing.section_mapper import SectionMapper


def test_alias_numbering_inline_and_page_continuation():
    result = SectionMapper().parse([
        (1, '문서 제목\n1. 업무 개요\n개요 본문\n2. 담당 업무\n업무 설명'),
        (2, '다음 페이지 이어짐\n[주의사항]: 삭제 금지\n참고자료\n매뉴얼'),
    ])
    assert [s.section_type for s in result] == ['other', 'overview', 'responsibilities', 'precautions', 'references']
    assert result[2].content == '업무 설명\n다음 페이지 이어짐'
    assert result[2].source_page == 1
    assert result[3].content == '삭제 금지'
    assert [s.sequence for s in result] == [1, 2, 3, 4, 5]


def test_unknown_heading_and_empty_page_preserve_text():
    mapper = SectionMapper()
    assert mapper.parse([(1, '\n  ')]) == []
    result = mapper.parse([(1, '주의사항을 먼저 읽으세요\n알 수 없는 제목\n내용')])
    assert len(result) == 1 and result[0].section_type == 'other'
    assert result[0].content == '주의사항을 먼저 읽으세요\n알 수 없는 제목\n내용'


def test_spaced_heading():
    assert SectionMapper().parse([(1, '3. 관 련 시 스 템\nDB')])[0].section_type == 'systems'


def test_item_mapping_only_explicit_fields():
    section = DocumentSection(id=12, document_id=3, section_type='responsibilities', section_title='주요 업무', sequence=1,
                              content='업무명: 백업\n설명: 로그 확인\n주기: 매일\n중요도: 5\n업무명: 복구\n설명: 복구 연습\n중요도: 9')
    items = map_handover_items(section)
    assert len(items) == 2
    assert items[0].task_name == '백업' and items[0].importance == 5
    assert items[0].frequency == '매일'
    assert items[0].category == 'responsibilities'
    assert items[0].document_id == 3 and items[0].section_id == 12
    assert items[1].importance is None
    assert items[0].precaution is None and items[0].related_system is None


def test_procedure_and_empty_section():
    section = DocumentSection(id=1, document_id=1, section_type='procedures', section_title='업무 절차', sequence=1, content='로그 확인\n백업 실행')
    item = map_handover_items(section)[0]
    assert item.procedure == section.content == item.description
    section.content = ''
    assert map_handover_items(section) == []


def test_contact_fields_do_not_create_duplicate_contact_section():
    result = SectionMapper().parse([(1, '담당자 및 연락처\n담당자: 홍길동\n연락처：ops@example.com')])
    assert len(result) == 1
    assert result[0].content == '담당자: 홍길동\n연락처：ops@example.com'
