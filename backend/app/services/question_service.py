from starlette.concurrency import run_in_threadpool

from app.core.exceptions import AppError
from app.llm.tasks.question_task import QuestionGenerationTask
from app.repositories.question_repository import QuestionRepository
from app.schemas.question import QuestionGenerationRequest, QuestionRead
from app.services.question_context import build_question_context
from app.services.retrieval_service import RetrievalService


class QuestionService:
    def __init__(self, repository: QuestionRepository, retrieval: RetrievalService, task: QuestionGenerationTask):
        self.repository, self.retrieval, self.task = repository, retrieval, task

    async def generate(self, request: QuestionGenerationRequest) -> list[QuestionRead]:
        if request.document_ids:
            await run_in_threadpool(self.repository.validate_documents, request.document_ids)
        query = (
            '문제 생성에 필요한 관련 원천 섹션을 찾아주세요. '
            'document_sections.id 또는 handover_items.section_id를 반드시 source_section_id 별칭으로 선택하세요. '
            'section ID를 임의 상수로 만들지 말고 관련 원문에서 조회하세요.\n'
            f'사용자 요청: {request.prompt}'
        )
        retrieved = await self.retrieval.search(query, document_ids=request.document_ids)
        ids = list(dict.fromkeys(row.get('source_section_id') for row in retrieved.rows
                                if type(row.get('source_section_id')) is int and row['source_section_id'] > 0))
        # Use canonical DB content, never a model-created SQL literal as evidence.
        rows = await run_in_threadpool(self.repository.sources, ids, request.document_ids)
        context = build_question_context(rows, self.retrieval.context_builder)
        if not context.source_documents:
            raise AppError('QUESTION_CONTEXT_EMPTY', '문제를 만들 수 있는 원천 섹션이 없습니다. 문서나 요청을 확인하세요.', 422)
        result = await self.task.generate(request, context)
        return await run_in_threadpool(self.repository.save_questions, result, context.source_documents)
