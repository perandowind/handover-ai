import logging
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from app.core.exceptions import AppError
from app.rendering.base import DocumentExporter, ExportedDocument
from app.rendering.template_renderer import TemplateRenderer
from app.schemas.generation import GeneratedDocument

logger = logging.getLogger(__name__)
MAX_PDF_BYTES = 20 * 1024 * 1024


class PdfExporter(DocumentExporter):
    def __init__(self, export_dir: Path, timeout_seconds: int = 60):
        self.export_dir = export_dir
        self.timeout_seconds = timeout_seconds
        self.renderer = TemplateRenderer()

    def export(self, document: GeneratedDocument) -> ExportedDocument:
        try:
            html = self.renderer.render(document)
            self.export_dir.mkdir(parents=True, exist_ok=True)
            # Private, unique request directory. No title-derived paths, shared
            # filenames, or persistent source HTML. Clean up on success/failure.
            with TemporaryDirectory(prefix='handover-export-', dir=self.export_dir) as directory:
                path = Path(directory) / 'handover.pdf'
                subprocess.run(
                    [sys.executable, str(Path(__file__).with_name('pdf_worker.py')), str(path)],
                    input=html.encode('utf-8'), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=self.timeout_seconds, check=True,
                )
                if not path.is_file() or not 0 < path.stat().st_size <= MAX_PDF_BYTES:
                    raise ValueError('Invalid PDF size')
                content = path.read_bytes()
                if not content.startswith(b'%PDF-'):
                    raise ValueError('Invalid PDF output')
            logger.info('PDF export completed bytes=%s', len(content))
            return ExportedDocument(content, 'handover.pdf', 'application/pdf')
        except subprocess.TimeoutExpired:
            logger.warning('PDF export timeout')
            raise AppError('PDF_EXPORT_FAILED', 'PDF 생성 시간이 초과되었습니다. 내용을 줄여 다시 시도하세요.', 504) from None
        except Exception as exc:
            logger.warning('PDF export failed type=%s', type(exc).__name__)
            raise AppError('PDF_EXPORT_FAILED', 'PDF를 생성하지 못했습니다. 잠시 후 다시 시도하세요.', 500) from None
