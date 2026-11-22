import json
from sqlalchemy import func, select
from src.config.database import Session
from src.constants.enums import Role, Status
from src.domain.ledger import demo_rows
from src.domain.spec import SPEC
from src.models.identity import User
from src.models.jobs import PairingBatch
from src.models.source import Dataset
from src.services.ledger import import_ledger
from src.utils.security import hash_password


def seed():
    with Session.begin() as db:
        for role in Role:
            if not db.get(User, role.value):
                db.add(User(username=role.value, role=role,
                            password_hash=hash_password(f'{role.value}-demo-2611')))

        rows = demo_rows()
        # import_ledger 内部负责数据集去重保存与发票/验收单落库；重复执行时数据集已存在则幂等跳过
        dataset, created, _stats = import_ledger(
            db, SPEC['default_dataset'], SPEC['sample_name'], rows, 'seed')

        queued = db.scalar(select(func.count()).select_from(PairingBatch)
                           .where(PairingBatch.status.in_([Status.QUEUED, Status.RUNNING, Status.COMPLETE])))
        batch_created = False
        if not queued:
            db.add(PairingBatch(name='初始对账批次（演示）', dataset_id=dataset.id, author='seed'))
            db.flush()
            batch_created = True

        return {'users': db.scalar(select(func.count()).select_from(User)),
                'datasets': db.scalar(select(func.count()).select_from(Dataset)),
                'seed_dataset_id': dataset.id, 'row_count': dataset.row_count,
                'checksum': dataset.checksum, 'created_dataset': created,
                'batch_created': batch_created}


if __name__ == '__main__':
    print(json.dumps(seed(), ensure_ascii=False))
