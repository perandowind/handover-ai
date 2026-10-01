from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.schemas.generation import GeneratedDocument


@dataclass(frozen=True)
class ExportedDocument:
    content: bytes
    filename: str
    media_type: str


class DocumentExporter(ABC):
    @abstractmethod
    def export(self, document: GeneratedDocument) -> ExportedDocument:
        raise NotImplementedError
