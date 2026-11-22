"""对账引擎与单据校验的单元测试，仅依赖标准库：

    cd backend && python3 -m unittest discover -s tests -v

同时兼容 pytest（CI 装有 pytest 时可直接 pytest backend/tests）。
"""

import unittest

from src.domain.ledger import demo_rows, late_rows, validate_rows
from src.domain.reconcile import (
    AMBIGUOUS,
    NO_COMBINATION,
    NOTE_SURPLUS,
    build_blocks,
    build_report,
    format_yuan,
    reconcile,
    to_cents,
)


def inv(code, amount):
    return {'invoice_id': code, 'amount_cents': to_cents(amount)}


def note(code, amount):
    return {'note_code': code, 'amount_cents': to_cents(amount)}


def block(invoices, notes, organization='机构A', period='2026-10'):
    return {'organization': organization, 'period': period,
            'invoices': invoices, 'notes': notes}


class MoneyTests(unittest.TestCase):
    def test_to_cents(self):
        self.assertEqual(to_cents('100'), 10000)
        self.assertEqual(to_cents('12.34'), 1234)
        self.assertEqual(format_yuan(1234), '12.34')

    def test_rejects_bad_amount(self):
        for bad in ('0', '-1', '1.234', 'abc', '1.001', '', True):
            with self.assertRaises(ValueError):
                to_cents(bad)


class EngineTests(unittest.TestCase):
    def test_unique_multi_note_match(self):
        result = reconcile([block([inv('I1', '100.00')],
                                  [note('N1', '60.00'), note('N2', '40.00')])])
        self.assertEqual(len(result['confirmed_groups']), 1)
        self.assertEqual(result['confirmed_groups'][0]['note_codes'], ['N1', 'N2'])
        self.assertEqual(result['pending_invoices'], [])
        self.assertEqual(result['pending_notes'], [])
        self.assertEqual(result['pending_groups'], [])

    def test_one_to_one_match(self):
        result = reconcile([block([inv('I', '500.00')], [note('N', '500.00')])])
        self.assertEqual(len(result['confirmed_groups']), 1)
        self.assertEqual(result['confirmed_groups'][0]['note_codes'], ['N'])

    def test_secondary_goal_prefers_more_claimed_notes(self):
        # {100} 用 1 张 vs {60,40} 用 2 张，配平发票数同为 1 → 取认领更多的方案
        result = reconcile([block([inv('I', '100.00')],
                                  [note('a', '100.00'), note('b', '60.00'), note('c', '40.00')])])
        self.assertEqual(len(result['confirmed_groups']), 1)
        self.assertEqual(result['confirmed_groups'][0]['note_codes'], ['b', 'c'])
        self.assertEqual(result['pending_notes'][0]['reason'], NOTE_SURPLUS)

    def test_true_ambiguity_all_pending(self):
        result = reconcile([block([inv('I1', '100.00'), inv('I2', '100.00')],
                                  [note('N1', '100.00'), note('N2', '100.00')])])
        self.assertEqual(result['confirmed_groups'], [])
        # 两张发票各两种配法 → 4 个待核整组，每个 option_count=2
        self.assertEqual(len(result['pending_groups']), 4)
        self.assertTrue(all(g['option_count'] == 2 for g in result['pending_groups']))
        self.assertTrue(all(i['reason'] == AMBIGUOUS for i in result['pending_invoices']))
        self.assertTrue(all(n['reason'] == AMBIGUOUS for n in result['pending_notes']))

    def test_partial_confirmation_only_consistent_groups(self):
        result = reconcile([block(
            [inv('I1', '100.00'), inv('I2', '100.00'), inv('I3', '30.00')],
            [note('N1', '100.00'), note('N2', '100.00'), note('N4', '30.00')])])
        self.assertEqual(len(result['confirmed_groups']), 1)
        self.assertEqual(result['confirmed_groups'][0]['invoice_id'], 'I3')
        self.assertEqual({i['invoice_id'] for i in result['pending_invoices']}, {'I1', 'I2'})
        self.assertEqual({n['note_code'] for n in result['pending_notes']}, {'N1', 'N2'})

    def test_maximize_balanced_invoices_first(self):
        result = reconcile([block(
            [inv('A', '100.00'), inv('B', '60.00'), inv('C', '40.00')],
            [note('x', '100.00'), note('y', '60.00'), note('z', '40.00')])])
        self.assertEqual(len(result['confirmed_groups']), 3)

    def test_no_combination_and_surplus_notes(self):
        result = reconcile([block([inv('I9', '99.99')],
                                  [note('M1', '50.00'), note('M2', '10.00')])])
        self.assertEqual(result['confirmed_groups'], [])
        self.assertEqual(result['pending_invoices'][0]['reason'], NO_COMBINATION)
        self.assertTrue(all(n['reason'] == NOTE_SURPLUS for n in result['pending_notes']))

    def test_organization_and_period_isolation(self):
        result = reconcile([
            block([inv('I1', '50.00')], [note('N1', '50.00')], 'A', '2026-10'),
            block([inv('I2', '50.00')], [note('N2', '50.00')], 'A', '2026-11'),
            block([inv('I3', '50.00')], [note('N3', '50.00')], 'B', '2026-10'),
        ])
        self.assertEqual(len(result['confirmed_groups']), 3)

    def test_note_count_guard(self):
        notes = [note(f'N{i}', '1.00') for i in range(19)]
        with self.assertRaises(ValueError):
            reconcile([block([inv('I', '19.00')], notes)])

    def test_state_budget_guard(self):
        # 8 张发票 × 18 张单据 = 210 万状态，超出预算，要求缩小结算期
        invoices = [inv(f'I{i}', '1.00') for i in range(8)]
        notes = [note(f'N{i}', '1.00') for i in range(18)]
        with self.assertRaises(ValueError):
            reconcile([block(invoices, notes)])

    def test_eighteen_notes_with_few_invoices_allowed(self):
        # 18 张单据但只有 1 张发票：状态数 26 万在预算内，应正常求解
        notes = [note(f'N{i:02d}', f'{i + 1}.00') for i in range(18)]
        result = reconcile([block([inv('I', '171.00')], notes)])
        self.assertEqual(len(result['confirmed_groups']), 1)
        self.assertEqual(len(result['confirmed_groups'][0]['note_codes']), 18)

    def test_large_group_within_budget(self):
        # 预算内的较大真实组合：多张发票 × 14 张单据应能正常求解
        invoices = [inv('A', '40.00'), inv('B', '50.00'), inv('C', '46.00')]
        notes = [note(f'N{i:02d}', f'{i + 1}.00') for i in range(14)]
        result = reconcile([block(invoices, notes)])
        self.assertIsInstance(result['confirmed_groups'], list)
        self.assertIsInstance(result['pending_invoices'], list)


class ReportAndLedgerTests(unittest.TestCase):
    def test_blocks_grouped_and_sorted(self):
        invoices = [
            {'invoice_id': 'I2', 'organization': 'B', 'settlement_period': '2026-11', 'amount_cents': 1},
            {'invoice_id': 'I1', 'organization': 'A', 'settlement_period': '2026-10', 'amount_cents': 1},
        ]
        notes = [{'note_code': 'N1', 'organization': 'A', 'settlement_period': '2026-10', 'amount_cents': 1}]
        blocks = build_blocks(invoices, notes)
        self.assertEqual([(b['organization'], b['period']) for b in blocks],
                         [('A', '2026-10'), ('B', '2026-11')])

    def test_demo_end_to_end_and_late_arrival(self):
        invoices, notes = validate_rows(demo_rows())
        self.assertEqual(len(invoices), 5)
        self.assertEqual(len(notes), 6)

        first = build_report(invoices, notes)
        confirmed = {g['invoice_id']: g['note_codes'] for g in first['confirmed_groups']}
        self.assertEqual(confirmed, {
            'INV-2610-01': ['YS-1001', 'YS-1002'],
            'INV-DJ-1101': ['YS-DJ-01'],
        })
        self.assertEqual(len(first['pending_groups']), 4)
        pending_inv = {i['invoice_id']: i['reason'] for i in first['pending_invoices']}
        self.assertEqual(pending_inv['INV-2611-03'], NO_COMBINATION)
        self.assertEqual({n['note_code'] for n in first['pending_notes']},
                         {'YS-1101', 'YS-1102', 'YS-1103'})

        # 已入账整组剔除后重算：保留已入账，剩余无可确认
        posted_invoices = {'INV-2610-01', 'INV-DJ-1101'}
        posted_notes = {'YS-1001', 'YS-1002', 'YS-DJ-01'}
        rest_inv = [i for i in invoices if i['invoice_id'] not in posted_invoices]
        rest_notes = [n for n in notes if n['note_code'] not in posted_notes]
        self.assertEqual(build_report(rest_inv, rest_notes)['confirmed_groups'], [])

        # 晚到验收单补齐：333.33 配平原先无组合的发票
        _, late_notes = validate_rows(late_rows())
        after = build_report(rest_inv, rest_notes + late_notes)
        confirmed_after = {g['invoice_id']: g['note_codes'] for g in after['confirmed_groups']}
        self.assertEqual(confirmed_after.get('INV-2611-03'), ['YS-1104'])
        self.assertNotIn('INV-2611-01', confirmed_after)
        self.assertNotIn('INV-2611-02', confirmed_after)

    def test_duplicate_document_rejected(self):
        rows = demo_rows()
        rows.append(dict(rows[0]))  # 重复发票行
        with self.assertRaises(ValueError):
            validate_rows(rows)

    def test_bad_period_rejected(self):
        rows = demo_rows()
        rows[0]['settlement_period'] = '2026/10'
        with self.assertRaises(ValueError):
            validate_rows(rows)


if __name__ == '__main__':
    unittest.main()
