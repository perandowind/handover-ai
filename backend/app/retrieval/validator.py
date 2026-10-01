import math
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, OptimizeError, ParseError, UnsupportedError
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
from sqlglot.optimizer.qualify import qualify

from app.retrieval.schema import RetrievalSchema


class SQLValidationError(ValueError):
    """Only a fixed code is returned to the model; never parser internals."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ValidatedSQL:
    sql: str
    row_limit: int


# Fail closed on syntax outside this small Prototype SELECT grammar. In particular,
# no arbitrary function calls, subqueries, CTEs, unions, windows, or table functions.
_ALLOWED_NODES = {
    exp.Select, exp.From, exp.Table, exp.TableAlias, exp.Identifier, exp.Column,
    exp.Star, exp.Alias, exp.Where, exp.Join, exp.And, exp.Or, exp.Not, exp.Paren,
    exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Is, exp.Null,
    exp.Boolean, exp.Literal, exp.Neg, exp.Between, exp.In, exp.Like, exp.Escape,
    exp.Order, exp.Ordered, exp.Group, exp.Having, exp.Distinct, exp.Limit,
    exp.Offset, exp.Lower, exp.Upper, exp.Length, exp.Coalesce,
    exp.Count, exp.Min, exp.Max, exp.Sum, exp.Avg,
}
ALLOWED_FUNCTIONS = frozenset({
    'lower', 'upper', 'length', 'coalesce', 'ifnull', 'count', 'min', 'max',
    'sum', 'avg', 'like',
})
MAX_SQL_CHARS = 10000


class SQLValidator:
    def __init__(self, schema: RetrievalSchema, max_rows: int = 100):
        if max_rows < 1:
            raise ValueError('max_rows must be positive')
        self.schema = schema
        self.max_rows = max_rows

    def validate(self, sql: str) -> ValidatedSQL:
        if not isinstance(sql, str) or not sql.strip() or len(sql) > MAX_SQL_CHARS:
            raise SQLValidationError('INVALID_SQL_LENGTH')
        try:
            statements = sqlglot.parse(sql, read='sqlite', error_level=ErrorLevel.RAISE)
            if len(statements) != 1:
                raise SQLValidationError('MULTIPLE_STATEMENTS')
            query = statements[0]
            if not isinstance(query, exp.Select):
                raise SQLValidationError('SELECT_ONLY')
            self._check_grammar(query)
            query = normalize_identifiers(query, dialect='sqlite')
            tables = list(query.find_all(exp.Table))
            if not tables:
                raise SQLValidationError('TABLE_REQUIRED')
            for table in tables:
                if (not isinstance(table.this, exp.Identifier) or table.db or table.catalog
                        or table.name not in self.schema.tables):
                    raise SQLValidationError('TABLE_NOT_ALLOWED')
            for column in query.find_all(exp.Column):
                if column.db or column.catalog:
                    raise SQLValidationError('COLUMN_NOT_ALLOWED')
            # Resolves aliases and unqualified names, rejects missing/ambiguous
            # columns, and expands * using only the same allowlisted ORM schema.
            query = qualify(
                query, dialect='sqlite', schema=self.schema.for_parser(),
                infer_schema=False, validate_qualify_columns=True,
                expand_stars=True, quote_identifiers=True, identify=True,
            )
            self._check_grammar(query)
            names = [name.casefold() for name in query.named_selects]
            if not names or len(names) != len(set(names)):
                raise SQLValidationError('UNIQUE_RESULT_NAMES_REQUIRED')
            aliases = {table.alias_or_name: table.name for table in query.find_all(exp.Table)}
            for column in query.find_all(exp.Column):
                if column.table:
                    table_name = aliases.get(column.table)
                    if table_name is None or column.name not in self.schema.columns(table_name):
                        raise SQLValidationError('COLUMN_NOT_ALLOWED')
                elif (column.name.casefold() not in names
                      or column.find_ancestor(exp.Order, exp.Group, exp.Having) is None):
                    # SQLGlot leaves some HAVING references unresolved. SQLite's
                    # double-quoted-string fallback must not turn typos into data.
                    raise SQLValidationError('COLUMN_NOT_ALLOWED')
            limit = self.max_rows
            if query.args.get('limit') is not None:
                limit = min(self._integer(query.args['limit'].expression), self.max_rows)
            if query.args.get('offset') is not None:
                self._integer(query.args['offset'].expression)
            query = query.limit(limit)
            return ValidatedSQL(
                query.sql(dialect='sqlite', comments=False, unsupported_level=ErrorLevel.RAISE), limit,
            )
        except (ParseError, OptimizeError, UnsupportedError, RecursionError) as exc:
            raise SQLValidationError('INVALID_SYNTAX_OR_COLUMN') from exc

    @staticmethod
    def _integer(node: exp.Expression) -> int:
        if not isinstance(node, exp.Literal) or node.is_string or not node.this.isdecimal():
            raise SQLValidationError('INVALID_LIMIT_OR_OFFSET')
        if len(node.this) > 19:
            raise SQLValidationError('INVALID_LIMIT_OR_OFFSET')
        value = int(node.this)
        if value > 2**63 - 1:
            raise SQLValidationError('INVALID_LIMIT_OR_OFFSET')
        return value

    @staticmethod
    def _check_grammar(query: exp.Select) -> None:
        nodes = list(query.walk())
        if len(nodes) > 500 or sum(isinstance(node, exp.Select) for node in nodes) != 1:
            raise SQLValidationError('UNSUPPORTED_SELECT')
        for node in nodes:
            if type(node) not in _ALLOWED_NODES:
                raise SQLValidationError('UNSUPPORTED_SELECT')
            if isinstance(node, exp.Join):
                if (node.args.get('side') not in (None, '', 'LEFT')
                        or node.args.get('kind') not in (None, '', 'INNER')
                        or node.args.get('method') or node.args.get('using')
                        or node.args.get('on') is None):
                    raise SQLValidationError('EXPLICIT_JOIN_REQUIRED')
            if isinstance(node, exp.Literal) and not node.is_string:
                try:
                    if not math.isfinite(float(node.this)):
                        raise SQLValidationError('INVALID_NUMBER')
                except ValueError as exc:
                    raise SQLValidationError('INVALID_NUMBER') from exc
