from datetime import datetime
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
from src.utils.time import now


class Invoice(Base):
    __tablename__ = 'invoices'
    __table_args__ = (UniqueConstraint('invoice_id'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[str] = mapped_column(String(40), index=True)
    organization: Mapped[str] = mapped_column(String(120), index=True)
    settlement_period: Mapped[str] = mapped_column(String(7), index=True)
    issued_on: Mapped[str] = mapped_column(String(10))
    amount_cents: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(String(120))
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=now)


class AcceptanceNote(Base):
    __tablename__ = 'acceptance_notes'
    __table_args__ = (UniqueConstraint('note_code'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    note_code: Mapped[str] = mapped_column(String(40), index=True)
    organization: Mapped[str] = mapped_column(String(120), index=True)
    settlement_period: Mapped[str] = mapped_column(String(7), index=True)
    issued_on: Mapped[str] = mapped_column(String(10))
    amount_cents: Mapped[int] = mapped_column(Integer)
    workshop: Mapped[str | None] = mapped_column(String(60))
    summary: Mapped[str | None] = mapped_column(String(120))
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=now)
