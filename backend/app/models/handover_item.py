from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class HandoverItem(CreatedAtMixin, Base):
    __tablename__ = "handover_items"
    __table_args__ = (CheckConstraint("importance BETWEEN 1 AND 5", name="importance"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("document_sections.id"), index=True)
    category: Mapped[str] = mapped_column(String)
    task_name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    procedure: Mapped[str | None] = mapped_column(Text)
    precaution: Mapped[str | None] = mapped_column(Text)
    importance: Mapped[int | None]
    frequency: Mapped[str | None] = mapped_column(String)
    related_system: Mapped[str | None] = mapped_column(String)
    contact_info: Mapped[str | None] = mapped_column(Text)
