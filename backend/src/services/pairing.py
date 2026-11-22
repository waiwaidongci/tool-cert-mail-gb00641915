import logging
from datetime import timedelta
from sqlalchemy import select
from src.config.database import Session
from src.constants.enums import Status
from src.domain.reconcile import build_report
from src.models.jobs import PairingBatch, PostedGroup
from src.models.ledger import AcceptanceNote, Invoice
from src.services import ledger as ledger_service
from src.services.audit import record
from src.utils.exports import write_report
from src.utils.time import now

log = logging.getLogger(__name__)


class StalePlan(Exception):
    """入账依据的批次结果已过期（单据在计算后发生变化），HTTP 层映射为 409。"""


def claim():
    stamp = now()
    with Session.begin() as db:
        query = select(PairingBatch).where(
            (PairingBatch.status == Status.QUEUED)
            | ((PairingBatch.status == Status.RUNNING) & (PairingBatch.lease_until < stamp)))
        job = db.scalar(query.order_by(PairingBatch.id).limit(1).with_for_update(skip_locked=True))
        if job is None:
            return None
        if job.attempt >= 3:
            job.status = Status.FAILED
            job.error = '后台进程多次中断，请发起新的对账批次'
            job.finished_at = stamp
            record(db, 'worker', 'reconcile.failed', job.id, reason=job.error)
            return None
        job.status = Status.RUNNING
        job.attempt += 1
        job.lease_until = stamp + timedelta(minutes=3)
        return job.id, job.attempt


def execute(lease):
    job_id, attempt = lease
    result = export = failure = None
    try:
        with Session() as db:
            invoices, notes = ledger_service.open_documents(db)
        result = build_report(invoices, notes)
        export = write_report(job_id, attempt, result)
    except ValueError as error:
        failure = str(error)[:500]
    except Exception:
        log.exception('Reconcile %s failed', job_id)
        failure = '计算失败，请检查单据口径后重试'

    with Session.begin() as db:
        job = db.get(PairingBatch, job_id, with_for_update=True)
        # 并发保护：只有仍持有本次租约的计算才能落结果，旧进程的迟到结果直接丢弃
        if job.attempt != attempt or job.status != Status.RUNNING:
            return
        job.lease_until = None
        job.finished_at = now()
        job.status = Status.FAILED if failure else Status.COMPLETE
        job.result = None if failure else result
        job.export_file = export
        job.error = failure
        record(db, 'worker', f'reconcile.{job.status}', job.id, attempt=attempt, reason=failure)


def post_confirmed(db, batch_id, actor, note=''):
    """把某批次建议确认的整组入账。整段在一个事务内，行锁 + 唯一约束保证不重复认领。"""
    job = db.get(PairingBatch, batch_id, with_for_update=True)
    if job is None:
        raise LookupError('找不到该对账批次')
    if job.status != Status.COMPLETE or not job.result:
        raise ValueError('只有计算完成的批次可以入账')

    groups = job.result.get('confirmed_groups', [])
    if not groups:
        raise ValueError('该批次没有方案一致的整组可入账')

    # 锁定本批涉及的发票与验收单，挡住并发入账与并发导入修改
    invoice_ids = [group['invoice_id'] for group in groups]
    note_codes = sorted({code for group in groups for code in group['note_codes']})
    db.scalars(select(Invoice).where(Invoice.invoice_id.in_(invoice_ids)).with_for_update()).all()
    db.scalars(select(AcceptanceNote).where(AcceptanceNote.note_code.in_(note_codes)).with_for_update()).all()

    existing_invoice = set(db.scalars(
        select(PostedGroup.invoice_id).where(PostedGroup.invoice_id.in_(invoice_ids))))
    existing_keys = set(db.scalars(
        select(PostedGroup.group_key).where(PostedGroup.group_key.in_([g['group_key'] for g in groups]))))

    # 重新基于当前待认领单据计算，检测「计算后单据已变动」的过期配法
    open_invoices, open_notes = ledger_service.open_documents(db)
    fresh = build_report(open_invoices, open_notes)
    fresh_by_invoice = {group['invoice_id']: group for group in fresh['confirmed_groups']}

    created, skipped = [], []
    for group in groups:
        if group['invoice_id'] in existing_invoice or group['group_key'] in existing_keys:
            # 重试场景：同一整组已入账，幂等跳过，绝不二次认领
            skipped.append(group['invoice_id'])
            continue
        current = fresh_by_invoice.get(group['invoice_id'])
        if current is None or current['group_key'] != group['group_key']:
            raise StalePlan(
                f"发票 {group['invoice_id']} 的配对依据已变化（单据被重新计算或修改），"
                '旧配法拒绝入账；请在最新批次结果上重新确认')
        db.add(PostedGroup(
            group_key=group['group_key'], batch_id=batch_id, invoice_id=group['invoice_id'],
            organization=group['organization'], settlement_period=group['period'],
            note_codes=group['note_codes'], amount_cents=group['amount_cents'],
            basis=group['basis'], author=actor))
        created.append(group['invoice_id'])

    if not created and skipped:
        record(db, actor, 'post.idempotent', batch_id, skipped=skipped, note=note)
        return {'posted': [], 'skipped': skipped, 'stale': []}

    record(db, actor, 'post.committed', batch_id, posted=created,
           skipped=skipped, note=note)
    return {'posted': created, 'skipped': skipped, 'stale': []}
