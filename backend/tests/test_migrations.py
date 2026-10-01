from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.core.config import BACKEND_DIR, get_settings
from app.db.base import Base
from app.db.session import create_db_engine


def test_upgrade_schema_consistency_and_downgrade(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv('DATABASE_URL', url)
    get_settings.cache_clear()
    config = Config(str(BACKEND_DIR / 'alembic.ini'))
    engine = create_db_engine(url)
    try:
        command.upgrade(config, 'head')
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {'alembic_version'}
        for name, table in Base.metadata.tables.items():
            assert {c['name']: c['nullable'] for c in inspector.get_columns(name)} == {
                c.name: c.nullable for c in table.columns
            }
        command.check(config)
        command.downgrade(config, 'base')
        assert inspect(engine).get_table_names() == ['alembic_version']
        command.upgrade(config, 'head')
        command.check(config)
    finally:
        engine.dispose()
        get_settings.cache_clear()
