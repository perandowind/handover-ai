from sqlalchemy import Boolean, CheckConstraint, ForeignKey, REAL, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class ScoringResult(CreatedAtMixin, Base):
    __tablename__ = "scoring_results"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="score"),
        CheckConstraint("scoring_method IN ('llm','python_fallback')", name="scoring_method"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    user_answer: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(REAL)
    is_correct: Mapped[bool | None] = mapped_column(Boolean(create_constraint=True, name="is_correct"))
    reason: Mapped[str | None] = mapped_column(Text)
    scoring_method: Mapped[str] = mapped_column(String)
