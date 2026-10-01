from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import BACKEND_DIR, Settings


def test_defaults_and_stable_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None)
    assert Path(make_url(settings.database_url).database) == BACKEND_DIR / 'data/app.db'
    assert settings.sql_model == settings.document_model == settings.question_model == settings.scoring_model == 'qwen3.5:4b'


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('CORS_ORIGINS', '["http://localhost:9999"]')
    monkeypatch.setenv('SQL_MODEL', 'future-model')
    monkeypatch.setenv('UPLOAD_DIR', './custom/uploads')
    settings = Settings(_env_file=None)
    assert settings.database_url == 'sqlite:///:memory:'
    assert settings.cors_origins == ['http://localhost:9999']
    assert settings.sql_model == 'future-model'
    assert settings.upload_dir == BACKEND_DIR / 'custom/uploads'


def test_reject_non_sqlite():
    with pytest.raises(ValidationError, match='requires SQLite'):
        Settings(_env_file=None, database_url='postgresql://localhost/db')
