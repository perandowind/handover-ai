import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.handover import HANDOVER_OUTLINE
from app.llm.provider import LLMProvider
from app.main import create_app
from app.rendering.base import DocumentExporter
from app.rendering.pdf_exporter import PdfExporter
from app.rendering.template_renderer import TemplateRenderer
from app.schemas.generation import GeneratedDocument


@pytest.fixture
def document():
    return GeneratedDocument.model_validate({'title': 'DB 운영 인수인계서', 'sections': [
        {'section_type': key, 'title': title, 'content': '관련 정보 없음'} for key, title in HANDOVER_OUTLINE
    ]})


@pytest.fixture
def exporter(tmp_path):
    return PdfExporter(tmp_path / 'exports')


def extract(content):
    with pymupdf.open(stream=content, filetype='pdf') as pdf:
        return ''.join(page.get_text() for page in pdf)


def test_real_pdf_has_korean_outline_page_numbers_and_embedded_font(exporter, document):
    before = document.model_dump()
    result = exporter.export(document)
    assert result.content.startswith(b'%PDF-')
    assert result.filename == 'handover.pdf' and result.media_type == 'application/pdf'
    with pymupdf.open(stream=result.content, filetype='pdf') as pdf:
        assert len(pdf) == 1
        text = pdf[0].get_text()
        assert document.title in text and '1 / 1' in text
        assert all(title in text for _, title in HANDOVER_OUTLINE)
        assert text.count('관련 정보 없음') == 8
        assert any('Droid Sans Fallback' in font[3] for font in pdf[0].get_fonts())
        assert pdf[0].rect.width == pytest.approx(595, abs=1)
    assert document.model_dump() == before
    assert list(exporter.export_dir.iterdir()) == []


def test_untrusted_text_is_escaped_not_interpreted(exporter, document, tmp_path):
    secret = tmp_path / 'secret.txt'
    secret.write_text('DO_NOT_READ_THIS_FILE')
    text = f'<script>alert(1)</script> <img src="file://{secret}"> <b>일반 텍스트</b> & {{7*7}}'
    document.sections[0].content = text
    document.title = '../../test <b>title</b>'
    html = TemplateRenderer().render(document)
    assert '<script>' not in html and '<img ' not in html and '&lt;script&gt;' in html
    output = exporter.export(document)
    extracted = extract(output.content).replace('\u200b', '').replace('\n', '')
    assert '<script>alert(1)</script>' in extracted and '<b>일반 텍스트</b>' in extracted
    assert 'DO_NOT_READ_THIS_FILE' not in extracted
    assert output.filename == 'handover.pdf'
    assert secret.read_text() == 'DO_NOT_READ_THIS_FILE'


def test_long_multiline_content_paginates_without_loss(exporter, document):
    lines = [f'항목 {index:03d}: 백업 결과를 확인하고 담당자에게 전달합니다.' for index in range(180)]
    document.sections[3].content = '\n'.join(lines)
    result = exporter.export(document)
    with pymupdf.open(stream=result.content, filetype='pdf') as pdf:
        assert len(pdf) >= 4
        text = ''.join(page.get_text() for page in pdf)
        assert all(line in text for line in lines)
        for index, page in enumerate(pdf):
            assert f'{index+1} / {len(pdf)}' in page.get_text()
            # Body and footer must remain inside the physical paper.
            for block in page.get_text('blocks'):
                assert block[0] >= 40 and block[2] <= page.rect.width - 40
                assert block[1] >= 35 and block[3] <= page.rect.height - 15


def test_long_unbroken_identifiers_wrap_inside_margins(exporter, document):
    document.title = 'W' * 180
    document.sections[0].content = 'W' * 4000
    result = exporter.export(document)
    with pymupdf.open(stream=result.content, filetype='pdf') as pdf:
        text = ''.join(page.get_text() for page in pdf).replace('\u200b', '').replace('\n', '').replace(' ', '')
        assert 'W' * 180 in text
        assert text.count('W') == 4180
        for page in pdf:
            for block in page.get_text('blocks'):
                assert block[0] >= 40 and block[2] <= page.rect.width - 40


@pytest.mark.parametrize('failure', ['process', 'timeout', 'missing', 'invalid', 'oversized'])
def test_failure_cleans_private_directory_and_returns_safe_error(exporter, document, monkeypatch, failure):
    import app.rendering.pdf_exporter as module
    def run(args, **kwargs):
        path = Path(args[-1])
        assert path.parent.parent == exporter.export_dir
        if failure == 'timeout':
            path.write_bytes(b'partial')
            raise subprocess.TimeoutExpired(args, 1)
        if failure == 'process':
            raise subprocess.CalledProcessError(1, args, stderr='private document')
        if failure == 'invalid': path.write_bytes(b'not a PDF')
        if failure == 'oversized': path.write_bytes(b'%PDF-' * 100)
    monkeypatch.setattr(module.subprocess, 'run', run)
    if failure == 'oversized': monkeypatch.setattr(module, 'MAX_PDF_BYTES', 10)
    with pytest.raises(AppError) as error:
        exporter.export(document)
    assert error.value.code == 'PDF_EXPORT_FAILED'
    assert error.value.status_code == (504 if failure == 'timeout' else 500)
    assert 'private' not in str(error.value)
    assert list(exporter.export_dir.iterdir()) == []


def test_parallel_exports_are_isolated_and_cleaned(exporter, document):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: exporter.export(document), range(2)))
    assert all(document.title in extract(result.content) for result in results)
    assert list(exporter.export_dir.iterdir()) == []


def test_exporter_interface_is_abstract():
    with pytest.raises(TypeError):
        DocumentExporter()


class NoLLM(LLMProvider):
    async def generate(self, **kwargs):
        pytest.fail('PDF export must not call an LLM or retrieve data')


@pytest.fixture
def client(tmp_path):
    settings = Settings(_env_file=None, database_url=f'sqlite:///{tmp_path / "unused.db"}',
                        export_dir=tmp_path/'exports')
    with TestClient(create_app(settings, llm_provider=NoLLM())) as client:
        yield client


def test_download_api_accepts_existing_generated_document_without_llm(client, document):
    response = client.post('/api/generation/handover/pdf', json=document.model_dump())
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['content-disposition'] == 'attachment; filename="handover.pdf"'
    assert response.headers['cache-control'] == 'no-store'
    assert document.title in extract(response.content)
    assert list(client.app.state.document_exporter.export_dir.iterdir()) == []


@pytest.mark.parametrize('change', ['missing', 'extra', 'empty', 'incorrect_title'])
def test_invalid_export_payload_never_reaches_renderer(client, document, monkeypatch, change):
    body = document.model_dump()
    if change == 'missing': body['sections'].pop()
    if change == 'extra': body['path'] = '/tmp/override.pdf'
    if change == 'empty': body['title'] = ' '
    if change == 'incorrect_title': body['sections'][0]['title'] = '다른 제목'
    monkeypatch.setattr(client.app.state.document_exporter, 'export', lambda _: pytest.fail('Invalid input rendered'))
    response = client.post('/api/generation/handover/pdf', json=body)
    assert response.status_code == 422 and response.json()['code'] == 'VALIDATION_ERROR'


def test_export_failure_uses_common_error_response(client, document, monkeypatch):
    def fail(_):
        raise AppError('PDF_EXPORT_FAILED', 'PDF 생성 실패', 500)
    monkeypatch.setattr(client.app.state.document_exporter, 'export', fail)
    response = client.post('/api/generation/handover/pdf', json=document.model_dump())
    assert response.status_code == 500
    assert response.json() == {'code': 'PDF_EXPORT_FAILED', 'message': 'PDF 생성 실패', 'detail': {}}


def test_worker_stops_at_page_budget(tmp_path, document, monkeypatch):
    import app.rendering.pdf_worker as worker
    monkeypatch.setattr(worker, 'MAX_PAGES', 1)
    document.sections[0].content = ('매일 백업 상태 확인\n' * 200).strip()
    with pytest.raises(ValueError, match='page limit'):
        worker.render_pdf(TemplateRenderer().render(document), tmp_path/'limit.pdf')
