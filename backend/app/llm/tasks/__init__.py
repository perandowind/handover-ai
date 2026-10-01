from app.core.config import Settings
from app.llm.tasks import document_task, question_task, scoring_task, sql_task
from app.llm.tasks.base import TaskDefinition


def configure_tasks(settings: Settings) -> dict[str, TaskDefinition]:
    tasks = [module.configure(settings) for module in (
        sql_task, document_task, question_task, scoring_task,
    )]
    return {task.name: task for task in tasks}
