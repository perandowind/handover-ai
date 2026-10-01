import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.db.session import create_db_engine
from app.schemas.common import ErrorResponse
from app.ocr.base import OcrEngine
from app.ocr.paddle_ocr import PaddleOcrAdapter
from app.ocr.pdf_renderer import PdfRenderer
from app.ocr.pipeline import DocumentPipeline
from app.parsing.section_mapper import SectionMapper, SectionParser
from app.services.document_service import DocumentService


def create_app(settings: Settings | None = None, *, ocr_engine: OcrEngine | None = None,
               section_parser: SectionParser | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=logging.DEBUG if settings.debug_logging else logging.INFO)
        engine = create_db_engine(settings.database_url)
        app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        app.state.settings = settings
        renderer = PdfRenderer(settings)
        app.state.document_service = DocumentService(settings, renderer)
        app.state.document_pipeline = DocumentPipeline(
            settings, app.state.session_factory, renderer,
            ocr_engine or PaddleOcrAdapter(settings), section_parser or SectionMapper(),
        )
        try:
            app.state.document_pipeline.recover_interrupted()
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="Handover AI", version="0.1.0", lifespan=lifespan,
        responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    register_exception_handlers(app)
    app.include_router(health_router, prefix="/api")
    app.include_router(documents_router, prefix="/api")
    return app


app = create_app()
