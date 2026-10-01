from starlette.concurrency import run_in_threadpool

from app.llm.tasks.sql_task import SQLGenerationTask
from app.retrieval.base import RetrievedData, RetrievalStrategy
from app.retrieval.executor import SQLiteReader


class SqlRetrievalStrategy(RetrievalStrategy):
    def __init__(self, task: SQLGenerationTask, reader: SQLiteReader):
        self.task = task
        self.reader = reader

    async def retrieve(self, query: str, *, document_ids: list[int] | None = None) -> RetrievedData:
        validated = await self.task.generate(query, document_ids=document_ids)
        rows = await run_in_threadpool(self.reader.execute, validated)
        return RetrievedData(rows=rows, sql=validated.sql)
