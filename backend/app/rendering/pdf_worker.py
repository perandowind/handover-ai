"""Isolated native renderer. Invoked by PdfExporter, not a network service."""
import sys
from pathlib import Path

import pymupdf

MAX_PAGES = 100


def render_pdf(html: str, destination: Path) -> None:
    page_rect = pymupdf.paper_rect('a4')
    content_rect = pymupdf.Rect(48, 48, page_rect.width - 48, page_rect.height - 54)
    story = pymupdf.Story(html=html)
    # No Archive is supplied: documents cannot load external images or files.
    writer = pymupdf.DocumentWriter(str(destination))
    try:
        for _ in range(MAX_PAGES):
            device = writer.begin_page(page_rect)
            more, _ = story.place(content_rect)
            story.draw(device)
            writer.end_page()
            if not more:
                break
        else:
            raise ValueError('PDF page limit exceeded')
    finally:
        writer.close()
    with pymupdf.open(destination) as pdf:
        total = len(pdf)
        for index, page in enumerate(pdf):
            page.insert_textbox(
                pymupdf.Rect(48, page_rect.height - 35, page_rect.width - 48, page_rect.height - 18),
                f'{index + 1} / {total}', fontsize=9, fontname='helv', align=1, color=(.4, .45, .5),
            )
        pdf.subset_fonts()
        content = pdf.tobytes(garbage=4, deflate=True)
    destination.write_bytes(content)


if __name__ == '__main__':
    try:
        render_pdf(sys.stdin.buffer.read().decode('utf-8'), Path(sys.argv[1]))
    except Exception:
        # Never print document HTML or native tracebacks to application logs.
        sys.exit(1)
