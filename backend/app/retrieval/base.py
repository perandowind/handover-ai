from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedData:
    rows: list[dict]
    sql: str | None = None


class RetrievalStrategy(ABC):
    @abstractmethod
    async def retrieve(self, query: str) -> RetrievedData:
        """Return ordered evidence rows without generating final documents."""
        raise NotImplementedError
