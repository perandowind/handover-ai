from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class Question(CreatedAtMixin, Base):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint("question_type IN ('multiple_choice','short_answer')", name="question_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), index=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("document_sections.id"), index=True)
    question_type: Mapped[str] = mapped_column(String)
    question_text: Mapped[str] = mapped_column(Text)
    choices_json: Mapped[str | None] = mapped_column(Text)
    correct_answer: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[str | None] = mapped_column(String)
