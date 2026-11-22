"""发票与车间验收单的配对引擎（纯标准库，金额一律按整数分计算）。

业务口径：
- 一张发票可配同机构、同结算期的一张或多张验收单；
- 配对金额必须精确到分（发票金额 == 验收单金额之和）；
- 每张单据只能被认领一次；
- 在所有可行配对中先尽量多配平发票（第一目标），再尽量多认领验收单（第二目标）；
- 枚举全部最优方案，只确认在每个最优方案中都出现的整组配对，
  其余整组与单据留待人工核对，并给出待核原因。

实现要点：不显式枚举可能指数爆炸的完整方案，而用 bitmask 动态规划计算
最优得分与最优方案数（Python 大整数精确计数），再用前向-后向方案数乘积统计
每个候选整组（发票 → 验收单子集）在多少个最优方案中出现：
出现次数等于最优方案总数即为「所有方案一致」，可确认入账。
"""

from decimal import Decimal, InvalidOperation

NO_COMBINATION = '无满足金额的验收单组合'
AMBIGUOUS = '存在多种最优配对，方案不一致'
NOTE_SURPLUS = '无对应待配发票'

CENTS = Decimal('100')
# 单个机构+结算期内参与计算的验收单上限，给出明确的单据数护栏
MAX_NOTES_PER_GROUP = 18
# 单组 DP 状态预算（发票数 × 2^验收单数）：实测该预算内最坏同额场景约 0.6 秒，
# 同时允许单张发票下达 18 张验收单；超出提示缩小结算期范围
STATE_BUDGET = 300_000


def to_cents(amount) -> int:
    """把两位小数字符串/数字金额转为整数分；非正数或超过两位小数一律拒绝。"""
    if isinstance(amount, bool):
        raise ValueError('金额格式不正确')
    try:
        text = str(amount).strip()
        value = Decimal(text)
        if not value.is_finite():
            raise ValueError
        rounded = value.quantize(Decimal('0.01'))
        if rounded != value:
            raise ValueError
    except (InvalidOperation, ValueError, ArithmeticError):
        raise ValueError('金额须为不超过两位小数的有效数字') from None
    if rounded <= 0:
        raise ValueError('金额必须为正数')
    return int(rounded * CENTS)


def format_yuan(cents: int) -> str:
    return f'{cents / 100:.2f}'


def _feasible_subsets(mask, target, amounts, bit_index, suffix_sum):
    """枚举 mask 内金额之和恰好等于 target 的所有子集（bitmask 列表），带后缀和剪枝。"""
    results = []
    chosen = []

    def dfs(position, remain):
        if remain == 0:
            sub = 0
            for j in chosen:
                sub |= 1 << j
            results.append(sub)
            return
        if position == len(bit_index) or remain > suffix_sum[position]:
            return
        index = bit_index[position]
        value = amounts[index]
        # 不选当前验收单
        dfs(position + 1, remain)
        # 选当前验收单
        if value <= remain:
            chosen.append(index)
            dfs(position + 1, remain - value)
            chosen.pop()

    dfs(0, target)
    return results


class _Solver:
    def __init__(self, invoice_amounts, note_amounts):
        self.invoices = invoice_amounts
        self.notes = note_amounts
        self.note_count = len(note_amounts)
        self.full_mask = (1 << self.note_count) - 1
        # 后向最优表：layers[i][mask] = (配平发票数, 认领验收单数, 最优方案数)
        self.layers = [dict() for _ in range(len(invoice_amounts) + 1)]
        # 每张发票的可行子集缓存
        self.transitions = [dict() for _ in range(len(invoice_amounts))]

    def _subsets_for(self, invoice_index, mask):
        cache = self.transitions[invoice_index]
        cached = cache.get(mask)
        if cached is not None:
            return cached
        target = self.invoices[invoice_index]
        bits = []
        cursor = mask
        while cursor:
            low = cursor & -cursor
            bits.append(low.bit_length() - 1)
            cursor ^= low
        suffix = [0] * (len(bits) + 1)
        for k in range(len(bits) - 1, -1, -1):
            suffix[k] = suffix[k + 1] + self.notes[bits[k]]
        subsets = tuple(_feasible_subsets(mask, target, self.notes, bits, suffix))
        cache[mask] = subsets
        return subsets

    def best(self, invoice_index, mask):
        """发票 invoice_index 起、可用验收单为 mask 时的 (最优得分, 精确方案数)。"""
        if invoice_index == len(self.invoices):
            return 0, 0, 1
        cached = self.layers[invoice_index].get(mask)
        if cached is not None:
            return cached

        best_inv = best_notes = -1
        best_ways = 0

        def absorb(inv_count, note_count, ways):
            nonlocal best_inv, best_notes, best_ways
            if inv_count > best_inv or (inv_count == best_inv and note_count > best_notes):
                best_inv, best_notes, best_ways = inv_count, note_count, ways
            elif inv_count == best_inv and note_count == best_notes:
                best_ways += ways

        # 该发票放弃配平
        absorb(*self.best(invoice_index + 1, mask))
        # 该发票用某个精确凑出金额的子集配平
        for sub in self._subsets_for(invoice_index, mask):
            tail_inv, tail_notes, tail_ways = self.best(invoice_index + 1, mask ^ sub)
            absorb(tail_inv + 1, tail_notes + sub.bit_count(), tail_ways)

        self.layers[invoice_index][mask] = (best_inv, best_notes, best_ways)
        return best_inv, best_notes, best_ways

    def occurrence_counts(self):
        """返回 (全局最优得分, 最优方案总数, {候选整组: 出现的最优方案数})。"""
        global_inv, global_notes, total_ways = self.best(0, self.full_mask)
        counts = {}
        # 前向分布：front[mask] = (已配平发票数, 已认领验收单数, 精确方案数)
        front = {self.full_mask: (0, 0, 1)}
        for invoice_index in range(len(self.invoices)):
            nxt = {}

            def merge(mask, inv_count, note_count, ways):
                current = nxt.get(mask)
                if current is None:
                    nxt[mask] = (inv_count, note_count, ways)
                    return
                if inv_count > current[0] or (inv_count == current[0] and note_count > current[1]):
                    nxt[mask] = (inv_count, note_count, ways)
                elif inv_count == current[0] and note_count == current[1]:
                    nxt[mask] = (inv_count, note_count, current[2] + ways)

            for mask, (used_inv, used_notes, front_ways) in front.items():
                # 跳过该发票的前缀延续
                merge(mask, used_inv, used_notes, front_ways)
                for sub in self._subsets_for(invoice_index, mask):
                    tail_inv, tail_notes, tail_ways = self.best(invoice_index + 1, mask ^ sub)
                    plan_inv = used_inv + 1 + tail_inv
                    plan_notes = used_notes + sub.bit_count() + tail_notes
                    merge(mask ^ sub, used_inv + 1, used_notes + sub.bit_count(), front_ways)
                    # 仅统计能拼成全局最优的整组
                    if plan_inv == global_inv and plan_notes == global_notes:
                        key = (invoice_index, sub)
                        counts[key] = counts.get(key, 0) + front_ways * tail_ways
            front = nxt
        return (global_inv, global_notes), total_ways, counts


def _enumerate(invoice_amounts, note_amounts):
    """返回 (最优得分, 最优方案总数, 候选整组出现次数, 发票数, 验收单数)。"""
    solver = _Solver(invoice_amounts, note_amounts)
    return solver.occurrence_counts()


def _group_key(organization, period, invoice_ids, note_codes):
    return f'{organization}|{period}|INV:{"+".join(invoice_ids)}|NOTE:{"+".join(note_codes)}'


def reconcile(blocks) -> dict:
    """blocks: 按 (机构, 结算期) 归并好的 {'organization','period','invoices','notes'} 列表。"""
    confirmed = []
    pending_groups = []
    pending_invoices = []
    pending_notes = []

    for block in blocks:
        organization = block['organization']
        period = block['period']
        invoices = block['invoices']
        notes = block['notes']
        if len(notes) > MAX_NOTES_PER_GROUP:
            raise ValueError(
                f'{organization} {period} 的验收单超过 {MAX_NOTES_PER_GROUP} 张，请缩小结算期范围后重算')
        if len(invoices) * (1 << len(notes)) > STATE_BUDGET:
            raise ValueError(
                f'{organization} {period} 的单据组合规模过大（{len(invoices)} 张发票、'
                f'{len(notes)} 张验收单），请缩小结算期范围后重算')

        _score, total_ways, counts = _enumerate(
            [item['amount_cents'] for item in invoices],
            [item['amount_cents'] for item in notes])

        # 每张发票在最优方案中出现过的不同配法
        options_per_invoice = {}
        confirmed_sigs = set()
        ambiguous_sigs = set()
        for (invoice_index, sub), hits in counts.items():
            invoice_id = invoices[invoice_index]['invoice_id']
            note_codes = tuple(notes[j]['note_code'] for j in range(len(notes)) if sub & (1 << j))
            signature = (invoice_id, note_codes)
            options_per_invoice[invoice_id] = options_per_invoice.get(invoice_id, 0) + 1
            if hits == total_ways:
                confirmed_sigs.add(signature)
            else:
                ambiguous_sigs.add(signature)

        confirmed_invoice_ids = set()
        confirmed_note_codes = set()
        for invoice_id, note_codes in sorted(confirmed_sigs):
            invoice = next(item for item in invoices if item['invoice_id'] == invoice_id)
            matched = [item for item in notes if item['note_code'] in note_codes]
            total = sum(item['amount_cents'] for item in matched)
            confirmed_invoice_ids.add(invoice_id)
            confirmed_note_codes.update(note_codes)
            confirmed.append({
                'group_key': _group_key(organization, period, [invoice_id], list(note_codes)),
                'organization': organization, 'period': period,
                'invoice_id': invoice_id, 'note_codes': list(note_codes),
                'amount_cents': total,
                'basis': f'同机构同结算期内，发票 {invoice_id} 金额 {format_yuan(invoice["amount_cents"])} 元，'
                         f'验收单 {"、".join(note_codes)} 合计 {format_yuan(total)} 元，金额精确到分相等；'
                         f'该整组在全部 {total_ways} 个最优配对方案中均出现，结论一致。',
            })

        for invoice_id, note_codes in sorted(ambiguous_sigs):
            invoice = next(item for item in invoices if item['invoice_id'] == invoice_id)
            pending_groups.append({
                'organization': organization, 'period': period,
                'invoice_id': invoice_id, 'note_codes': list(note_codes),
                'amount_cents': invoice['amount_cents'],
                'reason': AMBIGUOUS,
                'option_count': options_per_invoice[invoice_id],
            })

        for item in invoices:
            if item['invoice_id'] in confirmed_invoice_ids:
                continue
            ambiguous = any(sig[0] == item['invoice_id'] for sig in ambiguous_sigs)
            pending_invoices.append({
                **item, 'organization': organization, 'period': period,
                'reason': AMBIGUOUS if ambiguous else NO_COMBINATION,
            })

        for item in notes:
            if item['note_code'] in confirmed_note_codes:
                continue
            ambiguous = any(item['note_code'] in sig[1] for sig in ambiguous_sigs)
            pending_notes.append({
                **item, 'organization': organization, 'period': period,
                'reason': AMBIGUOUS if ambiguous else NOTE_SURPLUS,
            })

    return {
        'confirmed_groups': confirmed,
        'pending_groups': pending_groups,
        'pending_invoices': pending_invoices,
        'pending_notes': pending_notes,
    }


def build_blocks(invoices, notes):
    """把待认领发票与验收单按 (机构, 结算期) 归并为引擎所需分组，键排序保证结果稳定。"""
    grouped = {}
    for item in invoices:
        grouped.setdefault((item['organization'], item['settlement_period']),
                           {'organization': item['organization'],
                            'period': item['settlement_period'],
                            'invoices': [], 'notes': []})['invoices'].append(item)
    for item in notes:
        key = (item['organization'], item['settlement_period'])
        if key not in grouped:
            grouped[key] = {'organization': item['organization'], 'period': item['settlement_period'],
                            'invoices': [], 'notes': []}
        grouped[key]['notes'].append(item)
    blocks = list(grouped.values())
    for block in blocks:
        block['invoices'].sort(key=lambda item: item['invoice_id'])
        block['notes'].sort(key=lambda item: item['note_code'])
    blocks.sort(key=lambda block: (block['organization'], block['period']))
    return blocks


def _with_yuan(item, key='amount_cents'):
    return {**item, 'amount_yuan': format_yuan(item[key])}


def build_report(open_invoices, open_notes) -> dict:
    """对待认领单据做一次完整对账，产出班报结构（含依据与待核原因）。"""
    blocks = build_blocks(open_invoices, open_notes)
    outcome = reconcile(blocks)

    confirmed = [_with_yuan(group, 'amount_cents') for group in outcome['confirmed_groups']]
    pending_groups = [_with_yuan(group) for group in outcome['pending_groups']]
    pending_invoices = [_with_yuan(item) for item in outcome['pending_invoices']]
    pending_notes = [_with_yuan(item) for item in outcome['pending_notes']]

    total_invoices = len(open_invoices)
    total_notes = len(open_notes)
    matched_invoices = len(confirmed)
    matched_notes = sum(len(group['note_codes']) for group in confirmed)
    matched_cents = sum(group['amount_cents'] for group in confirmed)
    ready = bool(confirmed)

    if total_invoices == 0 and total_notes == 0:
        headline = '当前没有待认领单据，所有单据均已入账或尚未导入'
    elif ready:
        headline = (f'本轮建议确认 {matched_invoices} 张发票的整组配对，'
                    f'认领 {matched_notes} 张验收单，{len(pending_invoices)} 张发票、'
                    f'{len(pending_notes)} 张验收单待核')
    else:
        headline = f'没有方案一致的整组可入账，{len(pending_invoices)} 张发票与 {len(pending_notes)} 张验收单全部待核'

    return {
        'ready': ready,
        'headline': headline,
        'note': '金额按整数分精确比较，发票金额等于其名下验收单金额之和。'
                '先最大化配平发票数、再最大化认领验收单数，仅确认全部最优方案一致的整组；'
                '重算只纳入待认领单据，已入账配对原样保留。',
        'metrics': [
            {'label': '待认领发票', 'value': total_invoices, 'detail': '参与本轮计算的发票数'},
            {'label': '待认领验收单', 'value': total_notes, 'detail': '参与本轮计算的验收单数'},
            {'label': '建议确认整组', 'value': matched_invoices,
             'detail': f'覆盖 {matched_notes} 张验收单，合计 {format_yuan(matched_cents)} 元'},
            {'label': '待核发票', 'value': len(pending_invoices), 'detail': '无组合或最优方案不一致'},
            {'label': '待核验收单', 'value': len(pending_notes), 'detail': '歧义或无对应待配发票'},
        ],
        'confirmed_groups': confirmed,
        'pending_groups': pending_groups,
        'pending_invoices': pending_invoices,
        'pending_notes': pending_notes,
        'tables': [
            {
                'title': '建议确认整组（所有最优方案一致）',
                'columns': [
                    {'key': 'organization', 'label': '校准机构'},
                    {'key': 'period', 'label': '结算期'},
                    {'key': 'invoice_id', 'label': '发票编号'},
                    {'key': 'note_codes', 'label': '认领验收单'},
                    {'key': 'amount_yuan', 'label': '配平金额（元）'},
                    {'key': 'basis', 'label': '配对依据'},
                ],
                'rows': confirmed,
            },
            {
                'title': '待核整组（最优方案不一致）',
                'columns': [
                    {'key': 'organization', 'label': '校准机构'},
                    {'key': 'period', 'label': '结算期'},
                    {'key': 'invoice_id', 'label': '发票编号'},
                    {'key': 'note_codes', 'label': '候选验收单'},
                    {'key': 'amount_yuan', 'label': '金额（元）'},
                    {'key': 'option_count', 'label': '候选配法数'},
                    {'key': 'reason', 'label': '待核原因'},
                ],
                'rows': pending_groups,
            },
            {
                'title': '待核发票',
                'columns': [
                    {'key': 'invoice_id', 'label': '发票编号'},
                    {'key': 'organization', 'label': '校准机构'},
                    {'key': 'period', 'label': '结算期'},
                    {'key': 'amount_yuan', 'label': '金额（元）'},
                    {'key': 'reason', 'label': '待核原因'},
                ],
                'rows': pending_invoices,
            },
            {
                'title': '待核验收单',
                'columns': [
                    {'key': 'note_code', 'label': '验收单编号'},
                    {'key': 'organization', 'label': '校准机构'},
                    {'key': 'period', 'label': '结算期'},
                    {'key': 'workshop', 'label': '车间'},
                    {'key': 'amount_yuan', 'label': '金额（元）'},
                    {'key': 'reason', 'label': '待核原因'},
                ],
                'rows': pending_notes,
            },
        ],
        'charts': [{
            'title': '单据配对概况（张数）', 'kind': 'bar',
            'series': [
                {'label': '已确认发票', 'value': matched_invoices},
                {'label': '已认领验收单', 'value': matched_notes},
                {'label': '待核发票', 'value': len(pending_invoices)},
                {'label': '待核验收单', 'value': len(pending_notes)},
            ],
        }],
    }
