import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.ocr.paddle_ocr import OcrLine, PaddleOcrAdapter, normalize_results
from app.parsing.reading_order import page_text


def raw(texts=('업무 개요',), scores=(.98,), polys=None):
    return [{'res': {'rec_texts': list(texts), 'rec_scores': list(scores),
                     'rec_polys': polys if polys is not None else [[[1, 2], [90, 2], [90, 20], [1, 20]]],
                     'dt_polys': [], 'model_settings': {'retained': True}}}]


def test_normalization_preserves_text_confidence_and_recognition_polygon():
    result = normalize_results(raw())
    assert result[0].model_dump() == {'text': '업무 개요', 'confidence': .98,
                                     'bbox': [[1, 2], [90, 2], [90, 20], [1, 20]]}


@pytest.mark.parametrize('scores', [[], [1.1], [float('nan')]])
def test_invalid_ocr_output_rejected(scores):
    with pytest.raises((ValueError, ValidationError)):
        normalize_results(raw(scores=scores))


def test_invalid_polygon_rejected():
    with pytest.raises(ValidationError):
        normalize_results(raw(polys=[[[1, 2], [3, 4]]]))


def test_empty_page_is_valid():
    assert normalize_results(raw(texts=[], scores=[], polys=[])) == []


def test_adapter_uses_korean_v5_and_caches_engine(monkeypatch, tmp_path):
    calls = []
    class FakePaddle:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def predict(self, *, input):
            assert input.endswith('.png')
            return [SimpleNamespace(json=raw()[0])]
    monkeypatch.setitem(sys.modules, 'paddleocr', SimpleNamespace(PaddleOCR=FakePaddle))
    adapter = PaddleOcrAdapter(Settings(_env_file=None))
    assert calls == []
    assert adapter.recognize(tmp_path / '1.png') == raw()
    adapter.recognize(tmp_path / '2.png')
    assert len(calls) == 1
    assert calls[0]['text_detection_model_name'] == 'PP-OCRv5_mobile_det'
    assert calls[0]['text_recognition_model_name'] == 'korean_PP-OCRv5_mobile_rec'
    assert calls[0]['use_doc_unwarping'] is False
    assert calls[0]['text_rec_score_thresh'] == 0


def test_reading_order_joins_horizontal_fragments_without_modifying_raw():
    def box(text, x, y):
        return OcrLine(text=text, confidence=.9, bbox=[[x,y],[x+20,y],[x+20,y+12],[x,y+12]])
    lines = [box('개요', 90, 0), box('설명', 0, 40), box('업무', 40, 1), box('1.', 0, 0)]
    assert page_text(lines) == '1. 업무 개요\n설명'
    assert [line.text for line in lines] == ['개요', '설명', '업무', '1.']
