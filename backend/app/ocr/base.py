from pathlib import Path
from typing import Any, Protocol


class OcrEngine(Protocol):
    def recognize(self, image_path: Path) -> list[dict[str, Any]]:
        """Return lossless, JSON-serializable engine results for one page image."""
        ...
