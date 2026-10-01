import math
from pathlib import Path
from threading import RLock

import pymupdf

from app.core.config import Settings
from app.core.exceptions import AppError

# PyMuPDF is not thread safe; validation and rendering share this process-wide lock.
_pdf_lock = RLock()


class PdfRenderer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def validate(self, path: Path) -> int:
        try:
            with path.open('rb') as stream:
                if not stream.read(1024).lstrip().startswith(b'%PDF-'):
                    raise AppError('INVALID_PDF', 'PDF 파일 형식이 올바르지 않습니다.', 422)
            with _pdf_lock, pymupdf.open(path) as pdf:
                if not pdf.is_pdf or pdf.is_repaired:
                    raise AppError('INVALID_PDF', '손상된 PDF는 처리할 수 없습니다.', 422)
                if pdf.needs_pass or pdf.is_encrypted:
                    raise AppError('ENCRYPTED_PDF', '암호화된 PDF는 지원하지 않습니다.', 422)
                if not 1 <= pdf.page_count <= self.settings.max_pdf_pages:
                    raise AppError('PDF_PAGE_LIMIT', f'PDF는 1~{self.settings.max_pdf_pages}페이지여야 합니다.', 422)
                for page in pdf:
                    rect = page.rect
                    scale = self.settings.pdf_render_dpi / 72
                    pixels = math.ceil(rect.width * scale) * math.ceil(rect.height * scale)
                    if pixels <= 0 or pixels > self.settings.max_page_pixels:
                        raise AppError('PDF_PAGE_TOO_LARGE', '페이지 렌더링 크기 제한을 초과했습니다.', 422)
                return pdf.page_count
        except AppError:
            raise
        except (RuntimeError, ValueError, pymupdf.FileDataError) as exc:
            raise AppError('INVALID_PDF', 'PDF 파일을 열 수 없습니다.', 422) from exc

    def render_page(self, path: Path, page_number: int, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with _pdf_lock, pymupdf.open(path) as pdf:
            page = pdf[page_number - 1]
            page.get_pixmap(dpi=self.settings.pdf_render_dpi, colorspace=pymupdf.csRGB, alpha=False).save(output)
