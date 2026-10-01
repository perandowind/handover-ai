import json

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import Document, DocumentPage, DocumentSection, HandoverItem, Question, ScoringResult


def document():
    return Document(title='DB 운영', document_type='handover', source_filename='scan.pdf', source_path='uploads/scan.pdf')


def test_six_models_round_trip(session):
    doc = document()
    session.add(doc)
    session.flush()
    page = DocumentPage(document_id=doc.id, page_number=1, image_path='pages/1.png',
                        raw_text='백업 확인', ocr_json=json.dumps({'text': '백업 확인', 'confidence': .98, 'bbox': []}, ensure_ascii=False))
    section = DocumentSection(document_id=doc.id, section_type='procedures', section_title='업무 절차', content='백업 확인', sequence=1, source_page=1)
    session.add_all([page, section])
    session.flush()
    item = HandoverItem(document_id=doc.id, section_id=section.id, category='Database', task_name='백업', description='백업 확인', importance=5)
    question = Question(document_id=doc.id, section_id=section.id, question_type='multiple_choice', question_text='확인할 업무는?', choices_json='["백업", "배포"]', correct_answer='1')
    session.add_all([item, question])
    session.flush()
    result = ScoringResult(question_id=question.id, user_answer='1', score=100, is_correct=True, scoring_method='llm')
    session.add(result)
    session.commit()
    session.expire_all()
    assert doc.ocr_status == doc.parse_status == 'pending'
    assert doc.created_at and doc.updated_at
    assert doc.department is None
    assert json.loads(session.scalar(select(DocumentPage)).ocr_json)['text'] == '백업 확인'
    assert session.scalar(select(HandoverItem)).section_id == section.id
    assert session.scalar(select(ScoringResult)).score == 100
    assert session.scalar(select(Question)).explanation is None


def test_foreign_keys_reject_orphans(session):
    session.add(DocumentPage(document_id=999, page_number=1, image_path='x', raw_text='', ocr_json='[]'))
    with pytest.raises(IntegrityError):
        session.commit()


def test_deletion_does_not_silently_remove_source(session):
    doc = document()
    session.add(doc)
    session.flush()
    session.add(DocumentPage(document_id=doc.id, page_number=1, image_path='x', raw_text='', ocr_json='[]'))
    session.commit()
    session.delete(doc)
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize('value', [-1, 101])
def test_score_range(session, value):
    question = Question(question_type='short_answer', question_text='업무?', correct_answer='백업')
    session.add(question)
    session.flush()
    session.add(ScoringResult(question_id=question.id, user_answer='백업', score=value, scoring_method='python_fallback'))
    with pytest.raises(IntegrityError):
        session.commit()


def test_unique_page_number(session):
    doc = document()
    session.add(doc)
    session.flush()
    for _ in range(2):
        session.add(DocumentPage(document_id=doc.id, page_number=1, image_path='x', raw_text='', ocr_json='[]'))
    with pytest.raises(IntegrityError):
        session.commit()


def test_updated_at_changes_on_orm_update(session):
    doc = document()
    session.add(doc)
    session.commit()
    session.execute(text("UPDATE documents SET updated_at='2000-01-01 00:00:00' WHERE id=:id"), {'id': doc.id})
    session.commit()
    doc.title = '변경된 제목'
    session.commit()
    session.refresh(doc)
    assert doc.updated_at.year > 2000
