from app.retrieval.base import RetrievalStrategy
from app.retrieval.context import ContextBuilder
from app.schemas.retrieval import RetrievalResponse


class RetrievalService:
    def __init__(self, strategy: RetrievalStrategy, context_builder: ContextBuilder):
        self.strategy = strategy
        self.context_builder = context_builder

    async def search(self, query: str) -> RetrievalResponse:
        result = await self.strategy.retrieve(query)
        context = self.context_builder.build(result.rows)
        return RetrievalResponse(sql=result.sql or '', rows=result.rows,
                                 row_count=len(result.rows), context=context.text,
                                 context_truncated=context.truncated)
