import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import Settings


class OcrLine(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    text: str
    confidence: float = Field(ge=0, le=1)
    bbox: list[list[float]]

    @model_validator(mode='after')
    def validate_bbox(self):
        if len(self.bbox) != 4 or any(len(point) != 2 for point in self.bbox):
            raise ValueError('Expected a four-point polygon')
        return self


def normalize_results(results: list[dict[str, Any]]) -> list[OcrLine]:
    """Use recognition polygons, not detection polygons (which may differ in count)."""
    lines = []
    for result in results:
        data = result.get('res', result)
        texts, scores, boxes = data['rec_texts'], data['rec_scores'], data['rec_polys']
        if not len(texts) == len(scores) == len(boxes):
            raise ValueError('OCR result arrays have different lengths')
        lines.extend(OcrLine(text=text, confidence=score, bbox=box)
                     for text, score, box in zip(texts, scores, boxes, strict=True))
    return lines


class PaddleOcrAdapter:
    """Lazy CPU adapter. The document pipeline serializes access to this instance."""
    def __init__(self, settings: Settings):
        self.settings = settings
        self._engine = None

    def recognize(self, image_path: Path) -> list[dict[str, Any]]:
        if self._engine is None:
            from paddleocr import PaddleOCR

            self._engine = PaddleOCR(
                text_detection_model_name=self.settings.ocr_detection_model,
                text_recognition_model_name=self.settings.ocr_recognition_model,
                text_detection_model_dir=self.settings.ocr_detection_model_dir,
                text_recognition_model_dir=self.settings.ocr_recognition_model_dir,
                device='cpu', cpu_threads=self.settings.ocr_cpu_threads,
                enable_mkldnn=False,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                text_rec_score_thresh=0.0,
            )
        results = []
        for result in self._engine.predict(input=str(image_path)):
            # PaddleX's official JSON view converts numpy arrays/scalars losslessly.
            raw = result.json
            results.append(json.loads(raw) if isinstance(raw, str) else raw)
        if len(results) != 1:
            raise ValueError('Expected one OCR result for one image')
        return results
