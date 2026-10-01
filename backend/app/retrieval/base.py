from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedData:
    rows: list[dict]
    sql: str | None = None


class RetrievalStrategy(ABC):
    @abstractmethod
    async def retrieve(self, query: str, *, document_ids: list[int] | None = None) -> RetrievedData:
        """Return ordered evidence rows without generating final documents."""
        raise NotImplementedError
