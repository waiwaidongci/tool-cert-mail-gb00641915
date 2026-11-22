from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.config.database import connection
from src.constants.enums import Role
from src.controllers.auth import allow, current
from src.domain.spec import SPEC
from src.models.identity import User
from src.models.jobs import PostedGroup
from src.models.ledger import AcceptanceNote, Invoice
from src.models.source import Dataset
from src.schemas.requests import Upload
from src.services.audit import record
from src.services.datasets import template
from src.services.ledger import LedgerConflict, import_ledger
from src.services.validation import parse_rows
from src.utils import views

router = APIRouter()


@router.get('/spec')
def spec():
    return SPEC


@router.get('/template')
def sample(actor: User = Depends(current)):
    filename = quote(SPEC['sample_name'])
    return Response(template(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{filename}"})


@router.get('/datasets')
def datasets(db: Session = Depends(connection), actor: User = Depends(current)):
    return [views.dataset(item) for item in db.scalars(select(Dataset).order_by(Dataset.id.desc()).limit(100))]


@router.get('/datasets/{dataset_id}')
def details(dataset_id: int, offset: int = Query(0, ge=0), limit: int = Query(16, ge=1, le=100),
            db: Session = Depends(connection), actor: User = Depends(current)):
    item = db.get(Dataset, dataset_id)
    if not item:
        raise HTTPException(404, '找不到该数据批次')
    return {**views.dataset(item), 'rows': item.rows[offset:offset + limit]}


@router.post('/datasets', status_code=201)
def upload(body: Upload, db: Session = Depends(connection),
           actor: User = Depends(allow(Role.ADMIN, Role.ANALYST))):
    rows = parse_rows(body.csv_text)
    try:
        item, created, stats = import_ledger(db, body.name, body.filename, rows, actor.username)
    except LedgerConflict as error:
        db.rollback()
        raise HTTPException(409, str(error)) from None
    if created:
        record(db, actor.username, 'dataset.imported', item.id,
               rows=item.row_count, invoices=stats['invoices'], notes=stats['notes'],
               updated=stats['updated'], skipped=stats['skipped'])
    db.commit()
    return {**views.dataset(item), 'created': created, 'stats': stats}


@router.get('/documents/invoices')
def invoices(db: Session = Depends(connection), actor: User = Depends(current)):
    claimed = set(db.scalars(select(PostedGroup.invoice_id)))
    return [{**views.invoice(item), 'claimed': item.invoice_id in claimed}
            for item in db.scalars(select(Invoice).order_by(Invoice.id.desc()).limit(500))]


@router.get('/documents/notes')
def notes(db: Session = Depends(connection), actor: User = Depends(current)):
    claimed = set()
    for codes in db.scalars(select(PostedGroup.note_codes)):
        claimed.update(codes)
    return [{**views.note(item), 'claimed': item.note_code in claimed}
            for item in db.scalars(select(AcceptanceNote).order_by(AcceptanceNote.id.desc()).limit(500))]
