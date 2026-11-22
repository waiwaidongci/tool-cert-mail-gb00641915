from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.config.database import connection
from src.config.settings import ARTIFACTS
from src.constants.enums import Role
from src.controllers.auth import allow, current
from src.domain.reconcile import build_report
from src.domain.spec import SPEC
from src.models.identity import User
from src.models.jobs import PairingBatch, PostedGroup
from src.models.source import Dataset
from src.schemas.requests import BatchRequest, PostRequest
from src.services import ledger as ledger_service
from src.services.audit import record
from src.services.pairing import StalePlan, post_confirmed
from src.utils import views
from src.utils.wakeup import wake

router = APIRouter()


@router.get('/batches')
def index(db: Session = Depends(connection), actor: User = Depends(current)):
    items = db.scalars(select(PairingBatch).order_by(PairingBatch.id.desc()).limit(100))
    return [views.batch(item) for item in items]


@router.post('/batches', status_code=202)
def create(body: BatchRequest, db: Session = Depends(connection),
           actor: User = Depends(allow(Role.ADMIN, Role.ANALYST))):
    if not db.get(Dataset, body.dataset_id):
        raise HTTPException(404, '找不到指定的数据批次')
    item = PairingBatch(name=body.name, dataset_id=body.dataset_id, author=actor.username)
    db.add(item)
    db.flush()
    record(db, actor.username, 'reconcile.queued', item.id, dataset_id=item.dataset_id)
    db.commit()
    wake()
    return views.batch(item, detail=True)


@router.get('/batches/{batch_id}')
def detail(batch_id: int, db: Session = Depends(connection), actor: User = Depends(current)):
    item = db.get(PairingBatch, batch_id)
    if not item:
        raise HTTPException(404, '找不到该对账批次')
    return views.batch(item, detail=True)


@router.get('/batches/{batch_id}/export')
def export(batch_id: int, db: Session = Depends(connection), actor: User = Depends(current)):
    item = db.get(PairingBatch, batch_id)
    if not item:
        raise HTTPException(404, '找不到该对账批次')
    if not item.export_file:
        raise HTTPException(409, '此批次尚无可下载结果')
    path = ARTIFACTS / item.export_file
    if not path.is_file():
        raise HTTPException(410, '导出文件已不可用，请重新运行')
    return FileResponse(path, media_type='text/csv',
                        filename=f'{SPEC["short_name"]}-{item.id}.csv')


@router.post('/batches/{batch_id}/post')
def post(batch_id: int, body: PostRequest, db: Session = Depends(connection),
         actor: User = Depends(allow(Role.ADMIN))):
    try:
        outcome = post_confirmed(db, batch_id, actor.username, body.note)
    except LookupError as error:
        raise HTTPException(404, str(error)) from None
    except StalePlan as error:
        db.rollback()
        raise HTTPException(409, str(error)) from None
    db.commit()
    return outcome


@router.get('/posted')
def posted(db: Session = Depends(connection), actor: User = Depends(current)):
    items = db.scalars(select(PostedGroup).order_by(PostedGroup.id.desc()).limit(200))
    return [views.posted_group(item) for item in items]


@router.get('/report')
def report(db: Session = Depends(connection), actor: User = Depends(current)):
    """班报页面：已入账整组 + 当前待认领单据的实时待核原因。"""
    posted_items = [views.posted_group(item)
                    for item in db.scalars(select(PostedGroup).order_by(PostedGroup.id.desc()))]
    invoices, notes = ledger_service.open_documents(db)
    live = build_report(invoices, notes) if (invoices or notes) else None
    return {'posted_groups': posted_items, 'live': live}
