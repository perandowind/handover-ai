import logging
import math
import sqlite3
import time
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.exceptions import AppError
from app.retrieval.schema import RetrievalSchema
from app.retrieval.validator import ALLOWED_FUNCTIONS, ValidatedSQL

logger = logging.getLogger(__name__)


class SQLiteReader:
    """Dedicated read-only connection; never shares ORM write connections."""

    def __init__(self, database_url: str, schema: RetrievalSchema, max_rows: int,
                 timeout_seconds: float = 5):
        self.database = make_url(database_url).database
        self.schema = schema
        self.max_rows = max_rows
        self.timeout_seconds = timeout_seconds

    def _authorize(self, action, arg1, arg2, database, source):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            # SQLite may report database=None for an empty-column table read
            # (COUNT(*) and covering-index scans), even on the main database.
            table_read = arg2 == '' and database in (None, 'main')
            column_read = database == 'main' and arg1 in self.schema.tables and arg2 in self.schema.columns(arg1)
            if source is None and arg1 in self.schema.tables and (table_read or column_read):
                return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and arg2 in ALLOWED_FUNCTIONS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    def execute(self, query: ValidatedSQL) -> list[dict]:
        if not isinstance(query, ValidatedSQL):
            raise TypeError('SQLiteReader accepts only validated SQL')
        if not self.database or self.database == ':memory:':
            raise AppError('RETRIEVAL_DATABASE_UNSUPPORTED',
                           'SQL retrieval requires a file-backed SQLite database', 503)
        uri = Path(self.database).resolve().as_uri() + '?mode=ro'
        connection = None
        timed_out = False
        deadline = time.monotonic() + self.timeout_seconds

        def progress():
            nonlocal timed_out
            timed_out = time.monotonic() >= deadline
            return int(timed_out)

        try:
            connection = sqlite3.connect(uri, uri=True, timeout=self.timeout_seconds)
            connection.row_factory = sqlite3.Row
            # Trusted static setup, not model-generated SQL.
            connection.execute('PRAGMA query_only = ON')
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
            connection.set_authorizer(self._authorize)
            connection.set_progress_handler(progress, 1000)
            cursor = connection.execute(query.sql)
            rows = [dict(row) for row in cursor.fetchmany(min(query.row_limit, self.max_rows))] if query.row_limit else []
            for row in rows:
                if any(isinstance(value, float) and not math.isfinite(value) for value in row.values()):
                    raise AppError('RETRIEVAL_FAILED', 'Query returned a non-finite number', 502)
            logger.info('SQL retrieval completed row_count=%s', len(rows))
            return rows
        except sqlite3.Error as exc:
            logger.warning('SQL retrieval failed type=%s', type(exc).__name__)
            code = 'RETRIEVAL_TIMEOUT' if timed_out else 'RETRIEVAL_FAILED'
            raise AppError(code, 'Validated SQL could not be executed', 503) from exc
        finally:
            if connection is not None:
                connection.close()
