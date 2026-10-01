from starlette.concurrency import run_in_threadpool

from app.llm.tasks.sql_task import SQLGenerationTask
from app.retrieval.base import RetrievedData, RetrievalStrategy
from app.retrieval.executor import SQLiteReader


class SqlRetrievalStrategy(RetrievalStrategy):
    def __init__(self, task: SQLGenerationTask, reader: SQLiteReader):
        self.task = task
        self.reader = reader

    async def retrieve(self, query: str) -> RetrievedData:
        validated = await self.task.generate(query)
        rows = await run_in_threadpool(self.reader.execute, validated)
        return RetrievedData(rows=rows, sql=validated.sql)
