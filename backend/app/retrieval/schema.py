from app.models import Document, DocumentSection, HandoverItem


class RetrievalSchema:
    """One ORM-derived allowlist shared by prompts, validation, and execution."""

    def __init__(self):
        self.tables = {
            model.__table__.name: model.__table__
            for model in (Document, DocumentSection, HandoverItem)
        }

    def columns(self, table: str) -> set[str]:
        return set(self.tables[table].columns.keys())

    def for_parser(self) -> dict[str, dict[str, str]]:
        return {
            name: {column.name: str(column.type) for column in table.columns}
            for name, table in self.tables.items()
        }

    def describe(self) -> str:
        lines = ['Allowed tables (all other tables/columns are forbidden):']
        for name, table in self.tables.items():
            columns = []
            for column in table.columns:
                suffix = ' PRIMARY KEY' if column.primary_key else ''
                suffix += ' NULLABLE' if column.nullable else ' NOT NULL'
                for foreign_key in column.foreign_keys:
                    suffix += f' REFERENCES {foreign_key.target_fullname}'
                columns.append(f'  {column.name} {column.type}{suffix}')
            lines.append(f'{name}(\n' + ',\n'.join(columns) + '\n)')
        return '\n'.join(lines)
