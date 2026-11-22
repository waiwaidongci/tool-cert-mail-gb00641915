"""发票/验收单 CSV 行校验、领域对象转换与固定演练数据。"""

import re
from datetime import date

from .reconcile import to_cents
from .spec import ACCEPTANCE, INVOICE

PERIOD_PATTERN = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
MAX_PER_GROUP_HINT = 18


def _text(row, key, label, max_length):
    value = row.get(key)
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= max_length:
        raise ValueError(f'{label}须填写 1 至 {max_length} 个字符')
    return value.strip()


def _day(value, label):
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            pass
        else:
            if parsed.isoformat() == value:
                return value
    raise ValueError(f'{label}须为有效的 YYYY-MM-DD 日期')


def _period(value):
    if isinstance(value, str) and PERIOD_PATTERN.match(value.strip()):
        return value.strip()
    raise ValueError('结算期须为 YYYY-MM 格式，例如 2026-11')


def validate_rows(rows):
    """校验导入行并返回 (发票列表, 验收单列表)，编号在同类型内全局唯一。"""
    invoices = {}
    notes = {}
    for index, row in enumerate(rows, start=2):
        try:
            kind = row.get('record_type')
            document_id = _text(row, 'document_id', '单据编号', 40)
            organization = _text(row, 'organization', '校准机构', 120)
            period = _period(row.get('settlement_period'))
            issued_on = _day(row.get('issued_on'), '单据日期')
            amount_cents = to_cents(row.get('amount'))
            summary = row.get('summary')
            if summary is not None and not isinstance(summary, str):
                raise ValueError('摘要须为文本')
            summary = (summary or '').strip() or None

            if kind == INVOICE:
                if document_id in invoices:
                    raise ValueError(f'发票 {document_id} 重复')
                invoices[document_id] = {
                    'invoice_id': document_id, 'organization': organization,
                    'settlement_period': period, 'issued_on': issued_on,
                    'amount_cents': amount_cents, 'summary': summary,
                }
            elif kind == ACCEPTANCE:
                workshop = row.get('workshop')
                if workshop is not None and not isinstance(workshop, str):
                    raise ValueError('车间须为文本')
                workshop = (workshop or '').strip() or None
                if document_id in notes:
                    raise ValueError(f'验收单 {document_id} 重复')
                notes[document_id] = {
                    'note_code': document_id, 'organization': organization,
                    'settlement_period': period, 'issued_on': issued_on,
                    'amount_cents': amount_cents, 'workshop': workshop, 'summary': summary,
                }
            else:
                raise ValueError('记录类型须为校准机构发票或车间验收单')
        except ValueError as error:
            raise ValueError(f'CSV 第 {index} 行 · {error}') from None
    return list(invoices.values()), list(notes.values())


def demo_rows() -> list[dict]:
    """固定演练数据：两个机构、两个结算期，覆盖唯一配对、同额歧义、无组合与富余单。"""
    invoices = [
        # 岭南计量 · 2026-10：唯一整组 1200 = 720 + 480
        ('INV-2610-01', '岭南计量', '2026-10', '2026-10-28', '1200.00', '10 月校准服务费', None),
        # 岭南计量 · 2026-11：两张 500 发票，配两张 500 验收单 → 两种等价最优方案
        ('INV-2611-01', '岭南计量', '2026-11', '2026-11-25', '500.00', '11 月校准服务费（一）', None),
        ('INV-2611-02', '岭南计量', '2026-11', '2026-11-25', '500.00', '11 月校准服务费（二）', None),
        # 无任何组合的发票 333.33
        ('INV-2611-03', '岭南计量', '2026-11', '2026-11-26', '333.33', '加急校准费', None),
        # 东江检测院 · 2026-11：一对一 860
        ('INV-DJ-1101', '东江检测院', '2026-11', '2026-11-24', '860.00', '量具检测费', None),
    ]
    notes = [
        ('YS-1001', '岭南计量', '2026-10', '2026-10-20', '720.00', '机加工车间', '卡尺、千分尺校准验收'),
        ('YS-1002', '岭南计量', '2026-10', '2026-10-21', '480.00', '装配车间', '扭矩扳手校准验收'),
        ('YS-1101', '岭南计量', '2026-11', '2026-11-18', '500.00', '机加工车间', '11 月卡尺校准验收'),
        ('YS-1102', '岭南计量', '2026-11', '2026-11-19', '500.00', '终检车间', '11 月量规校准验收'),
        # 富余验收单：150 元，无对应待配发票
        ('YS-1103', '岭南计量', '2026-11', '2026-11-20', '150.00', '装配车间', '压力表单项校准验收'),
        ('YS-DJ-01', '东江检测院', '2026-11', '2026-11-17', '860.00', '终检车间', '电子天平检测验收'),
    ]
    rows = []
    for document_id, organization, period, issued_on, amount, summary, _ in invoices:
        rows.append(dict(record_type=INVOICE, document_id=document_id, organization=organization,
                         settlement_period=period, issued_on=issued_on, amount=amount,
                         workshop=None, summary=summary))
    for document_id, organization, period, issued_on, amount, workshop, summary in notes:
        rows.append(dict(record_type=ACCEPTANCE, document_id=document_id, organization=organization,
                         settlement_period=period, issued_on=issued_on, amount=amount,
                         workshop=workshop, summary=summary))
    return rows


def late_rows() -> list[dict]:
    """晚到补齐批次：补一张 333.33 元验收单，正好配平此前无组合的 INV-2611-03。"""
    return [
        dict(record_type=ACCEPTANCE, document_id='YS-1104', organization='岭南计量',
             settlement_period='2026-11', issued_on='2026-11-27', amount='333.33',
             workshop='终检车间', summary='晚到补录：高度规加急校准验收'),
    ]
