import pytest
import sqlglot

from app.retrieval.schema import RetrievalSchema
from app.retrieval.validator import SQLValidationError, SQLValidator


@pytest.fixture
def validator():
    return SQLValidator(RetrievalSchema(), max_rows=100)


@pytest.mark.parametrize('sql', [
    "INSERT INTO handover_items (task_name) VALUES ('x')",
    "UPDATE handover_items SET task_name='x'",
    'DELETE FROM handover_items', 'DROP TABLE documents',
    'ALTER TABLE documents ADD COLUMN x TEXT', 'CREATE TABLE x (id INT)',
    "REPLACE INTO documents (id) VALUES (1)", 'PRAGMA table_info(documents)',
    "ATTACH DATABASE '/tmp/other.db' AS other", 'DETACH DATABASE other',
    'BEGIN', 'COMMIT', 'VACUUM', 'EXPLAIN SELECT * FROM documents',
    'SELECT * FROM handover_items; DROP TABLE documents',
    'SELECT * FROM handover_items; SELECT * FROM documents',
    'SELECT * FROM handover_items; -- comment\n DELETE FROM documents',
    '/* benign */ dRoP TABLE documents',
])
def test_required_blocked_commands(validator, sql):
    with pytest.raises(SQLValidationError):
        validator.validate(sql)


@pytest.mark.parametrize('sql', [
    'SELECT * FROM nonexistent_table', 'SELECT * FROM sqlite_master',
    'SELECT * FROM document_pages', 'SELECT * FROM questions', 'SELECT * FROM scoring_results',
    'SELECT nonexistent_column FROM handover_items',
    'SELECT "nonexistent_column" FROM handover_items',
    'SELECT task_name FROM handover_items WHERE missing = 1',
    'SELECT task_name FROM handover_items ORDER BY missing',
    'SELECT task_name FROM handover_items GROUP BY missing',
    'SELECT task_name FROM handover_items HAVING missing = 1',
    'SELECT x.task_name FROM handover_items h',
    'SELECT id FROM handover_items h JOIN documents d ON d.id=h.document_id',
    'SELECT h.id FROM handover_items h JOIN documents d ON d.missing=h.document_id',
    'SELECT * FROM main.documents', 'SELECT * FROM temp.documents',
    'SELECT main.documents.id FROM documents',
    'SELECT rowid FROM documents',
])
def test_unknown_or_forbidden_tables_and_columns(validator, sql):
    with pytest.raises(SQLValidationError):
        validator.validate(sql)


@pytest.mark.parametrize('sql', [
    'WITH x AS (SELECT * FROM documents) SELECT * FROM x',
    'SELECT * FROM (SELECT * FROM documents)',
    'SELECT * FROM documents WHERE id IN (SELECT document_id FROM handover_items)',
    'SELECT * FROM documents UNION SELECT * FROM documents',
    "SELECT load_extension('/tmp/x') FROM documents",
    "SELECT readfile('/etc/passwd') FROM documents",
    'SELECT randomblob(100000000) FROM documents',
    "SELECT * FROM pragma_table_info('documents')",
    'SELECT sqlite_version() FROM documents',
    'SELECT * FROM documents CROSS JOIN handover_items',
    'SELECT * FROM documents, handover_items',
    'SELECT * FROM documents NATURAL JOIN handover_items',
    'SELECT id, id FROM documents', 'SELECT 1',
    'SELECT id FROM documents LIMIT -1', 'SELECT id FROM documents LIMIT 1+1',
    "SELECT id FROM documents LIMIT '10'", 'SELECT id FROM documents LIMIT ?',
    'SELECT id FROM documents LIMIT 10 OFFSET -1',
    'SELECT id FROM documents LIMIT 999999999999999999999',
    'SELECT 1e999 FROM documents', 'SELECT :value FROM documents',
    '', ';', 'SELECT', 'x' * 10001,
])
def test_unsupported_or_unbounded_expressions_fail_closed(validator, sql):
    with pytest.raises(SQLValidationError):
        validator.validate(sql)


@pytest.mark.parametrize('sql,expected', [
    ('SELECT task_name, description FROM handover_items', 100),
    ('SELECT * FROM handover_items LIMIT 999', 100),
    ('SELECT task_name FROM handover_items LIMIT 3', 3),
    ('SELECT task_name FROM handover_items LIMIT 0', 0),
    ('SELECT task_name FROM handover_items LIMIT 2 OFFSET 1', 2),
    ('SELECT task_name FROM handover_items LIMIT 1, 2', 2),
    ('sEleCt TASK_NAME FROM HANDOVER_ITEMS;', 100),
    ("SELECT task_name FROM handover_items WHERE description LIKE '%DROP; PRAGMA%'", 100),
    ('SELECT /* DELETE FROM documents */ task_name FROM handover_items', 100),
    ('SELECT h.task_name, d.title FROM handover_items h LEFT JOIN documents d ON d.id=h.document_id', 100),
    ('SELECT COUNT(*) AS count FROM handover_items', 100),
    ('SELECT category, COUNT(*) AS n FROM handover_items GROUP BY category HAVING COUNT(*)>0 ORDER BY n DESC', 100),
    ("SELECT task_name FROM handover_items WHERE importance BETWEEN 1 AND 5 AND category IN ('DB','Infra')", 100),
    ("SELECT COALESCE(precaution, '없음') AS precaution FROM handover_items WHERE section_id IS NOT NULL", 100),
])
def test_valid_selects_are_canonicalized_and_bounded(validator, sql, expected):
    result = validator.validate(sql)
    assert result.row_limit == expected
    parsed = sqlglot.parse_one(result.sql, read='sqlite')
    assert int(parsed.args['limit'].expression.this) == expected
    assert '--' not in result.sql and '/*' not in result.sql


def test_schema_is_derived_from_whitelisted_orm_models():
    schema = RetrievalSchema()
    assert set(schema.tables) == {'documents', 'document_sections', 'handover_items'}
    text = schema.describe()
    assert 'document_id INTEGER NOT NULL REFERENCES documents.id' in text
    assert 'precaution TEXT NULLABLE' in text
    assert 'document_pages' not in text
    assert 'questions' not in text
