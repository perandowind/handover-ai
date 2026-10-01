from app.core.config import Settings
from app.llm.client import StructuredLLMClient
from app.llm.tasks.sql_task import SQLGenerationTask, configure
from app.retrieval.context import ContextBuilder
from app.retrieval.executor import SQLiteReader
from app.retrieval.schema import RetrievalSchema
from app.retrieval.sql_strategy import SqlRetrievalStrategy
from app.retrieval.validator import SQLValidator
from app.services.retrieval_service import RetrievalService


def create_retrieval_service(settings: Settings, client: StructuredLLMClient) -> RetrievalService:
    schema = RetrievalSchema()
    validator = SQLValidator(schema, settings.max_retrieval_rows)
    task = SQLGenerationTask(client, configure(settings), schema, validator)
    reader = SQLiteReader(settings.database_url, schema, settings.max_retrieval_rows,
                          settings.retrieval_timeout_seconds)
    return RetrievalService(
        SqlRetrievalStrategy(task, reader),
        ContextBuilder(settings.max_retrieval_rows, settings.max_context_chars),
    )
