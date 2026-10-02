import json

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import AppError
from app.models import Document, DocumentSection, Question, ScoringResult
from app.schemas.llm import LLMScoringResult, QuestionGenerationResult
from app.schemas.question import QuestionData, QuestionRead
from app.schemas.scoring import ScoringResult as ScoringRead


class QuestionRepository:
    """Short transactions; no ORM session is held across an LLM request."""
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    @staticmethod
    def _data(row: Question) -> QuestionData:
        return QuestionData(
            id=row.id, document_id=row.document_id, section_id=row.section_id,
            question_type=row.question_type, question_text=row.question_text,
            choices=json.loads(row.choices_json) if row.choices_json else None,
            correct_answer=row.correct_answer, explanation=row.explanation, created_at=row.created_at,
        )

    def validate_documents(self, ids: list[int]) -> None:
        with self.session_factory() as session:
            for document_id in ids:
                document = session.get(Document, document_id)
                if document is None:
                    raise AppError('DOCUMENT_NOT_FOUND', '문서를 찾을 수 없습니다.', 404)
                if document.ocr_status != 'completed' or document.parse_status != 'completed':
                    raise AppError('DOCUMENT_NOT_READY', 'OCR과 구조화가 완료된 문서를 선택하세요.', 409)

    def sources(self, ids: list[int], document_ids: list[int] | None) -> list[dict]:
        if not ids:
            return []
        with self.session_factory() as session:
            statement = select(DocumentSection).join(Document).where(
                DocumentSection.id.in_(ids), Document.ocr_status == 'completed', Document.parse_status == 'completed',
            )
            if document_ids:
                statement = statement.where(DocumentSection.document_id.in_(document_ids))
            found = {row.id: {'source_section_id': row.id, 'document_id': row.document_id,
                             'section_title': row.section_title[:200], 'content': row.content}
                     for row in session.scalars(statement)}
            return [found[id] for id in ids if id in found and found[id]['content'].strip()]

    def save_questions(self, result: QuestionGenerationResult, source_documents: dict[int, int]) -> list[QuestionRead]:
        with self.session_factory() as session:
            rows = []
            for item in result.questions:
                section_id = item.source_section_id
                # Recheck provenance in the write transaction, including readiness.
                section = session.get(DocumentSection, section_id)
                if section is None or section.document_id != source_documents[section_id]:
                    raise AppError('QUESTION_SOURCE_CHANGED', '원천 문서가 변경되었습니다. 다시 생성하세요.', 409)
                source = session.get(Document, section.document_id)
                if source is None or source.ocr_status != 'completed' or source.parse_status != 'completed':
                    raise AppError('DOCUMENT_NOT_READY', '원천 문서가 준비되지 않았습니다.', 409)
                row = Question(document_id=section.document_id, section_id=section_id,
                               question_type=item.question_type, question_text=item.question,
                               choices_json=json.dumps(item.choices, ensure_ascii=False) if item.choices else None,
                               correct_answer=item.correct_answer, explanation=item.explanation)
                session.add(row)
                rows.append(row)
            session.flush()
            output = [QuestionRead.model_validate(self._data(row).model_dump()) for row in rows]
            session.commit()
            return output

    def list(self, offset: int, limit: int) -> list[QuestionRead]:
        with self.session_factory() as session:
            rows = session.scalars(select(Question).order_by(Question.id.desc()).offset(offset).limit(limit))
            return [QuestionRead.model_validate(self._data(row).model_dump()) for row in rows]

    def get(self, question_id: int) -> QuestionData:
        with self.session_factory() as session:
            row = session.get(Question, question_id)
            if row is None:
                raise AppError('QUESTION_NOT_FOUND', '문제를 찾을 수 없습니다.', 404)
            return self._data(row)

    def save_score(self, question_id: int, answer: str, result: LLMScoringResult, method: str) -> ScoringRead:
        with self.session_factory() as session:
            row = ScoringResult(question_id=question_id, user_answer=answer,
                                scoring_method=method, **result.model_dump())
            session.add(row)
            session.flush()
            output = ScoringRead(id=row.id, question_id=question_id, scoring_method=method, **result.model_dump())
            session.commit()
            return output
