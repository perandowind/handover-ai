from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class DocumentSection(CreatedAtMixin, Base):
    __tablename__ = "document_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    section_type: Mapped[str] = mapped_column(String)
    section_title: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    sequence: Mapped[int]
    source_page: Mapped[int | None]
