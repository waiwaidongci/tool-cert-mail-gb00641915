from datetime import datetime
from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
from src.constants.enums import Status
from src.utils.time import now


class PairingBatch(Base):
    """一次对账计算批次，结果快照与租约都落在该行。"""
    __tablename__ = 'pairing_batches'

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default=Status.QUEUED, index=True)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(500))
    export_file: Mapped[str | None] = mapped_column(String(100))
    attempt: Mapped[int] = mapped_column(default=0)
    lease_until: Mapped[datetime | None]
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=now)
    finished_at: Mapped[datetime | None]


class PostedGroup(Base):
    """已入账整组：发票与验收单一经入账即锁定，重算不再参与。"""
    __tablename__ = 'posted_groups'
    __table_args__ = (
        UniqueConstraint('invoice_id'),
        UniqueConstraint('group_key'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_key: Mapped[str] = mapped_column(String(220))
    batch_id: Mapped[int] = mapped_column(ForeignKey('pairing_batches.id'))
    invoice_id: Mapped[str] = mapped_column(String(40))
    organization: Mapped[str] = mapped_column(String(120), index=True)
    settlement_period: Mapped[str] = mapped_column(String(7), index=True)
    note_codes: Mapped[list] = mapped_column(JSON)
    amount_cents: Mapped[int] = mapped_column(Integer)
    basis: Mapped[str] = mapped_column(String(800))
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=now)
