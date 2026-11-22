from sqlalchemy import select
from src.domain import ledger
from src.models.jobs import PostedGroup
from src.models.ledger import AcceptanceNote, Invoice
from src.services.datasets import save


class LedgerConflict(Exception):
    """已认领单据被新批次改动时抛出，HTTP 层映射为 409。"""


def import_ledger(db, name, filename, rows, actor):
    """保存原始批次并把发票/验收单落库。

    - 同编号已存在且内容一致：幂等跳过；
    - 同编号内容变化但该单已入账：拒绝并提示，避免破坏已入账配对；
    - 同编号内容变化且仍待认领：更新为最新值；
    - 新编号：插入。
    返回 (dataset, created, 统计)。
    """
    dataset, created = save(db, name, filename, rows, actor)
    if not created:
        return dataset, False, {'invoices': 0, 'notes': 0, 'updated': 0, 'skipped': len(rows)}

    invoice_rows, note_rows = ledger.validate_rows(rows)

    incoming_invoice_ids = [item['invoice_id'] for item in invoice_rows]
    incoming_note_codes = [item['note_code'] for item in note_rows]

    # 先锁定本次涉及的现有单据行，与入账事务的行锁互斥，
    # 避免「读取认领状态后、更新前」并发入账导致覆盖已认领单据。
    locked_invoices = {
        item.invoice_id: item
        for item in db.scalars(select(Invoice).where(Invoice.invoice_id.in_(incoming_invoice_ids))
                               .with_for_update())
    }
    locked_notes = {
        item.note_code: item
        for item in db.scalars(select(AcceptanceNote).where(AcceptanceNote.note_code.in_(incoming_note_codes))
                               .with_for_update())
    }

    # 锁内读取认领状态：并发入账要么已提交（此处可见），要么在等行锁（无法中途提交）
    claimed_invoice_ids = set(db.scalars(select(PostedGroup.invoice_id)
                                          .where(PostedGroup.invoice_id.in_(incoming_invoice_ids))))
    claimed_note_codes = set()
    for codes in db.scalars(select(PostedGroup.note_codes)):
        claimed_note_codes.update(codes)

    stats = {'invoices': 0, 'notes': 0, 'updated': 0, 'skipped': 0}

    for payload in invoice_rows:
        current = locked_invoices.get(payload['invoice_id'])
        if current is None:
            db.add(Invoice(dataset_id=dataset.id, author=actor, **payload))
            stats['invoices'] += 1
            continue
        same = all(getattr(current, key) == payload[key] for key in
                   ('organization', 'settlement_period', 'issued_on', 'amount_cents', 'summary'))
        if same:
            stats['skipped'] += 1
            continue
        if payload['invoice_id'] in claimed_invoice_ids:
            raise LedgerConflict(f'发票 {payload["invoice_id"]} 已入账配对，不能被新批次修改；'
                                 '如需更正请先处理对应入账记录')
        for key, value in payload.items():
            setattr(current, key, value)
        current.dataset_id = dataset.id
        current.author = actor
        stats['updated'] += 1

    for payload in note_rows:
        current = locked_notes.get(payload['note_code'])
        if current is None:
            db.add(AcceptanceNote(dataset_id=dataset.id, author=actor, **payload))
            stats['notes'] += 1
            continue
        same = all(getattr(current, key) == payload[key] for key in
                   ('organization', 'settlement_period', 'issued_on', 'amount_cents',
                    'workshop', 'summary'))
        if same:
            stats['skipped'] += 1
            continue
        if payload['note_code'] in claimed_note_codes:
            raise LedgerConflict(f'验收单 {payload["note_code"]} 已入账配对，不能被新批次修改；'
                                 '如需更正请先处理对应入账记录')
        for key, value in payload.items():
            setattr(current, key, value)
        current.dataset_id = dataset.id
        current.author = actor
        stats['updated'] += 1

    return dataset, True, stats


def open_documents(db):
    """读取全部待认领（未入账）发票与验收单，转为引擎所需字典。"""
    claimed_invoice_ids = set(db.scalars(select(Invoice.invoice_id).join(
        PostedGroup, PostedGroup.invoice_id == Invoice.invoice_id)))
    claimed_note_codes = set()
    for codes in db.scalars(select(PostedGroup.note_codes)):
        claimed_note_codes.update(codes)

    invoices = [
        {'invoice_id': item.invoice_id, 'organization': item.organization,
         'settlement_period': item.settlement_period, 'issued_on': item.issued_on,
         'amount_cents': item.amount_cents, 'summary': item.summary}
        for item in db.scalars(select(Invoice).order_by(Invoice.invoice_id))
        if item.invoice_id not in claimed_invoice_ids
    ]
    notes = [
        {'note_code': item.note_code, 'organization': item.organization,
         'settlement_period': item.settlement_period, 'issued_on': item.issued_on,
         'amount_cents': item.amount_cents, 'workshop': item.workshop, 'summary': item.summary}
        for item in db.scalars(select(AcceptanceNote).order_by(AcceptanceNote.note_code))
        if item.note_code not in claimed_note_codes
    ]
    return invoices, notes
