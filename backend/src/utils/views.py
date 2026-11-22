from src.domain.reconcile import format_yuan
from src.utils.time import iso


def dataset(item):
    return {'id': item.id, 'name': item.name, 'filename': item.filename, 'row_count': item.row_count,
            'checksum': item.checksum, 'author': item.author, 'created_at': iso(item.created_at)}


def batch(item, detail=False):
    view = {'id': item.id, 'dataset_id': item.dataset_id, 'name': item.name, 'status': item.status,
            'author': item.author, 'created_at': iso(item.created_at),
            'finished_at': iso(item.finished_at), 'has_export': bool(item.export_file),
            'error': item.error,
            'confirmed_count': len(item.result.get('confirmed_groups', [])) if item.result else 0,
            'pending_invoice_count': len(item.result.get('pending_invoices', [])) if item.result else 0,
            'pending_note_count': len(item.result.get('pending_notes', [])) if item.result else 0}
    if detail:
        view['result'] = item.result
    return view


def invoice(item):
    return {'id': item.id, 'invoice_id': item.invoice_id, 'organization': item.organization,
            'settlement_period': item.settlement_period, 'issued_on': item.issued_on,
            'amount_cents': item.amount_cents, 'amount_yuan': format_yuan(item.amount_cents),
            'summary': item.summary, 'dataset_id': item.dataset_id, 'author': item.author,
            'created_at': iso(item.created_at)}


def note(item):
    return {'id': item.id, 'note_code': item.note_code, 'organization': item.organization,
            'settlement_period': item.settlement_period, 'issued_on': item.issued_on,
            'amount_cents': item.amount_cents, 'amount_yuan': format_yuan(item.amount_cents),
            'workshop': item.workshop, 'summary': item.summary, 'dataset_id': item.dataset_id,
            'author': item.author, 'created_at': iso(item.created_at)}


def posted_group(item):
    return {'id': item.id, 'group_key': item.group_key, 'batch_id': item.batch_id,
            'invoice_id': item.invoice_id, 'organization': item.organization,
            'settlement_period': item.settlement_period, 'note_codes': item.note_codes,
            'amount_cents': item.amount_cents, 'amount_yuan': format_yuan(item.amount_cents),
            'basis': item.basis, 'author': item.author, 'created_at': iso(item.created_at)}
