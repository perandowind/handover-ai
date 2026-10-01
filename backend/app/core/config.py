from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "development"
    debug_logging: bool = False
    database_url: str = "sqlite:///./data/app.db"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_seconds: int = Field(default=120, gt=0)
    sql_model: str = "qwen3.5:4b"
    document_model: str = "qwen3.5:4b"
    question_model: str = "qwen3.5:4b"
    scoring_model: str = "qwen3.5:4b"
    pdf_export_timeout_seconds: int = Field(default=60, gt=0)
    pdf_render_dpi: int = Field(default=200, ge=72, le=300)
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    max_pdf_pages: int = Field(default=30, gt=0)
    max_page_pixels: int = Field(default=25_000_000, gt=0)
    ocr_detection_model: str = "PP-OCRv5_mobile_det"
    ocr_recognition_model: str = "korean_PP-OCRv5_mobile_rec"
    ocr_detection_model_dir: str | None = None
    ocr_recognition_model_dir: str | None = None
    ocr_cpu_threads: int = Field(default=4, ge=1, le=32)
    upload_dir: Path = BACKEND_DIR / "data/uploads"
    page_image_dir: Path = BACKEND_DIR / "data/pages"
    ocr_result_dir: Path = BACKEND_DIR / "data/ocr"
    export_dir: Path = BACKEND_DIR / "data/exports"
    max_retrieval_rows: int = Field(default=100, gt=0)
    retrieval_timeout_seconds: float = Field(default=5, gt=0, allow_inf_nan=False)
    max_context_chars: int = Field(default=20000, gt=0)

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        url = urlsplit(value)
        if (url.scheme not in {"http", "https"} or not url.hostname
                or url.username is not None or url.password is not None
                or url.query or url.fragment or any(char.isspace() for char in value)):
            raise ValueError("OLLAMA_BASE_URL must be an HTTP(S) URL without credentials, query, or fragment")
        if url.port is not None and not 1 <= url.port <= 65535:
            raise ValueError("OLLAMA_BASE_URL must be an HTTP(S) URL without credentials, query, or fragment")
        return value

    @field_validator("sql_model", "document_model", "question_model", "scoring_model")
    @classmethod
    def nonempty_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("LLM model name must not be empty")
        return value.strip()

    @field_validator("database_url")
    @classmethod
    def normalize_sqlite_url(cls, value: str) -> str:
        url = make_url(value)
        if url.drivername not in {"sqlite", "sqlite+pysqlite"}:
            raise ValueError("Prototype v1 requires SQLite")
        if url.query:
            raise ValueError("SQLite URL query options are not supported in Phase 1")
        if url.database and url.database != ":memory:":
            path = Path(url.database)
            if not path.is_absolute():
                path = BACKEND_DIR / path
            url = url.set(database=str(path.resolve()))
        return url.render_as_string(hide_password=False)

    @field_validator("upload_dir", "page_image_dir", "ocr_result_dir", "export_dir")
    @classmethod
    def normalize_data_path(cls, value: Path) -> Path:
        return value.resolve() if value.is_absolute() else (BACKEND_DIR / value).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
