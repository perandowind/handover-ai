from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import AppError
from app.llm.tasks.document_task import DocumentGenerationTask
from app.repositories.document_repository import DocumentRepository
from app.schemas.generation import GeneratedDocument, HandoverGenerationRequest
from app.services.retrieval_service import RetrievalService


class HandoverGenerationService:
    def __init__(self, retrieval: RetrievalService, task: DocumentGenerationTask,
                 session_factory: sessionmaker[Session]):
        self.retrieval = retrieval
        self.task = task
        self.session_factory = session_factory

    def _check_documents(self, document_ids: list[int]) -> None:
        with self.session_factory() as session:
            repository = DocumentRepository(session)
            for document_id in document_ids:
                document = repository.get(document_id)
                if document.ocr_status != 'completed' or document.parse_status != 'completed':
                    raise AppError('DOCUMENT_NOT_READY', '선택한 문서의 OCR과 구조화 완료 후 다시 시도하세요.', 409)

    async def generate(self, request: HandoverGenerationRequest) -> GeneratedDocument:
        if request.document_ids:
            await run_in_threadpool(self._check_documents, request.document_ids)
        # Ask for actual source fields needed by the outline, not an answer or
        # fabricated SQL literals. Only the bounded Context reaches generation.
        query = (
            '다음 요청의 인수인계서 작성을 위한 원문을 검색하세요. '
            '관련 업무의 설명, 관련 시스템, 절차, 주의사항, 장애 대응, 연락처, 참고자료를 '
            '가능한 범위에서 조회하세요. 집계나 임의의 문자열을 생성하지 말고 DB의 원문 컬럼을 선택하세요.\n'
            f'사용자 요청: {request.prompt}'
        )
        result = await self.retrieval.search(query, document_ids=request.document_ids)
        return await self.task.generate(request.prompt, result.context,
                                        context_truncated=result.context_truncated)
