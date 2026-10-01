from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, utc_now


class Document(CreatedAtMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("ocr_status IN ('pending','processing','completed','failed')", name="ocr_status"),
        CheckConstraint("parse_status IN ('pending','completed','failed')", name="parse_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String)
    document_type: Mapped[str] = mapped_column(String)
    department: Mapped[str | None] = mapped_column(String)
    source_filename: Mapped[str] = mapped_column(String)
    source_path: Mapped[str] = mapped_column(String)
    ocr_status: Mapped[str] = mapped_column(String, default="pending", server_default="pending")
    parse_status: Mapped[str] = mapped_column(String, default="pending", server_default="pending")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, server_default=func.current_timestamp()
    )


class DocumentPage(CreatedAtMixin, Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number"),
        CheckConstraint("page_number >= 1", name="page_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    page_number: Mapped[int]
    image_path: Mapped[str] = mapped_column(String)
    raw_text: Mapped[str] = mapped_column(Text)
    ocr_json: Mapped[str] = mapped_column(Text)
