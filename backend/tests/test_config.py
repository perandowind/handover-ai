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


@pytest.mark.parametrize('url', ['ftp://localhost:11434', 'localhost:11434', 'http://',
                                 'http://user:password@localhost:11434',
                                 'http://localhost:11434?token=secret', 'http://localhost:11434#fragment',
                                 'http://local host:11434', 'http://localhost:99999', 'http://localhost:0',
                                 'http://@localhost:11434'])
def test_invalid_ollama_url(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ollama_base_url=url)


def test_ollama_url_and_timeout_overrides(monkeypatch):
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11435/')
    monkeypatch.setenv('OLLAMA_TIMEOUT_SECONDS', '15')
    config = Settings(_env_file=None)
    assert config.ollama_base_url == 'http://127.0.0.1:11435'
    assert config.ollama_timeout_seconds == 15


@pytest.mark.parametrize('field', ['sql_model', 'document_model', 'question_model', 'scoring_model'])
def test_model_name_cannot_be_empty(field):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: '  '})


@pytest.mark.parametrize('timeout', [0, -1])
def test_timeout_must_be_positive(timeout):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ollama_timeout_seconds=timeout)
