# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import tools, fields
from odoo.tests import common
from odoo.modules.module import get_resource_path
from odoo.exceptions import UserError, ValidationError, MissingError
from odoo.tools import float_compare, date_utils
from odoo.tests.common import Form
from odoo.addons.account_reports.tests.common import _init_options


import datetime
from dateutil.relativedelta import relativedelta
from freezegun import freeze_time
from unittest.mock import patch

def today():
    # 31'st of december is a particular date because entries are configured
    # to be autoposted on that day. The test values dont take it into account
    # so we just mock the date and run the 31'st as if it was the 30'th
    today = fields.Date.today()
    if today.month == 12 and today.day == 31:
        today += relativedelta(day=30)
    return today

class TestAccountAsset(common.TransactionCase):

    @patch('odoo.fields.Date.today', return_value=today())
    def setUp(self, today_mock):
        super(TestAccountAsset, self).setUp()
        self.registry.enter_test_mode(self.cr)
        self.addCleanup(self.registry.leave_test_mode)
        self._load('account', 'test', 'account_minimal_test.xml')
        today = fields.Date.today()
        self.truck = self.env['account.asset'].create({
            'account_asset_id': self.env.ref('account_asset.a_expense').id,
            'account_depreciation_id': self.env.ref('account_asset.a_expense').id,
            'account_depreciation_expense_id': self.env.ref('account_asset.cas').id,
            'journal_id': self.env.ref('account_asset.miscellaneous_journal').id,
            'asset_type': 'purchase',
            'name': 'truck',
            'acquisition_date': today + relativedelta(years=-6, month=1, day=1),
            'original_value': 10000,
            'salvage_value': 2500,
            'method_number': 10,
            'method_period': '12',
            'method': 'linear',
        })
        self.truck.validate()
        self.env['account.move']._autopost_draft_entries()
        self.assert_counterpart_account_id = self.env.ref('account_asset.a_sale').id

    def _load(self, module, *args):
        tools.convert_file(self.cr, 'account_asset',
                           get_resource_path(module, *args),
                           {}, 'init', False, 'test', self.registry._assertion_report)

    def update_form_values(self, asset_form):
        for i in range(len(asset_form.depreciation_move_ids)):
            with asset_form.depreciation_move_ids.edit(i) as line_edit:
                line_edit.asset_remaining_value

    def test_00_account_asset(self):
        """Test the lifecycle of an asset"""
        self.env.context = {**self.env.context, **{'asset_type': 'purchase'}}
        self._load('account', 'test', 'account_minimal_test.xml')
        self._load('account_asset', 'test', 'account_asset_demo_test.xml')

        CEO_car = self.browse_ref("account_asset.account_asset_vehicles_test0")
        # In order to get the fields from the model, I need to trigger the onchange method.
        CEO_car._onchange_model_id()

        # In order to test the process of Account Asset, I perform a action to confirm Account Asset.
        CEO_car.validate()

        # I check Asset is now in Open state.
        self.assertEqual(self.browse_ref("account_asset.account_asset_vehicles_test0").state, 'open',
                         'Asset should be in Open state')

        # I compute depreciation lines for asset of CEOs Car.
        self.assertEqual(CEO_car.method_number, len(CEO_car.depreciation_move_ids),
                         'Depreciation lines not created correctly')

        # Check that auto_post is set on the entries, in the future, and we cannot post them.
        with self.assertRaises(UserError):
            CEO_car.depreciation_move_ids.post()

        # I Check that After creating all the moves of depreciation lines the state "Running".
        CEO_car.depreciation_move_ids.write({'auto_post': False})
        CEO_car.depreciation_move_ids.post()
        self.assertEqual(self.browse_ref("account_asset.account_asset_vehicles_test0").state, 'open',
                         'State of asset should be runing')

        closing_invoice = self.env['account.move'].create({
            'type': 'out_invoice',
            'invoice_line_ids': [(0, 0, {
                'debit': 100,
            })]
        })

        with self.assertRaises(UserError, msg="You shouldn't be able to close if there are posted entries in the future"):
            CEO_car.set_to_close(closing_invoice.invoice_line_ids)

    def test_01_account_asset(self):
        """ Test if an an asset is created when an invoice is validated with an
        item on an account for generating entries.
        """
        self.env.context = {**self.env.context, **{'asset_type': 'purchase'}}
        self._load('account', 'test', 'account_minimal_test.xml')
        self._load('account_asset', 'test', 'account_deferred_revenue_demo_test.xml')

        # The account needs a default model for the invoice to validate the revenue
        self.browse_ref("account_asset.xfa").create_asset = 'validate'
        self.browse_ref("account_asset.xfa").asset_model = self.ref("account_asset.account_asset_model_sale_test0")

        invoice = self.env['account.move'].with_context(asset_type='purchase').create({
            'type': 'in_invoice',
            'partner_id': self.ref("base.res_partner_12"),
            'invoice_line_ids': [(0, 0, {
                'name': 'Insurance claim',
                'account_id': self.ref("account_asset.xfa"),
                'price_unit': 450,
                'quantity': 1,
            })],
        })
        invoice.post()

        recognition = invoice.asset_ids
        self.assertEqual(len(recognition), 1, 'One and only one recognition sould have been created from invoice.')

        # I confirm revenue recognition.
        recognition.validate()
        self.assertTrue(recognition.state == 'open',
                        'Recognition should be in Open state')
        first_invoice_line = invoice.invoice_line_ids[0]
        self.assertEqual(recognition.original_value, first_invoice_line.price_subtotal,
                         'Recognition value is not same as invoice line.')

        recognition.depreciation_move_ids.write({'auto_post': False})
        recognition.depreciation_move_ids.post()

        # I check data in move line and installment line.
        first_installment_line = recognition.depreciation_move_ids.sorted(lambda r: r.id)[0]
        self.assertAlmostEqual(first_installment_line.asset_remaining_value, recognition.original_value - first_installment_line.amount_total,
                               msg='Remaining value is incorrect.')
        self.assertAlmostEqual(first_installment_line.asset_depreciated_value, first_installment_line.amount_total,
                               msg='Depreciated value is incorrect.')

        # I check next installment date.
        last_installment_date = first_installment_line.date
        installment_date = last_installment_date + relativedelta(months=+int(recognition.method_period))
        self.assertEqual(recognition.depreciation_move_ids.sorted(lambda r: r.id)[1].date, installment_date,
                         'Installment date is incorrect.')

    @patch('odoo.fields.Date.today', return_value=today())
    def test_02_account_asset(self, today_mock):
        """Test the selling of a fully depreciated asset with gain"""
        self.env.context = {**self.env.context, **{'asset_type': 'purchase'}}
        self._load('account', 'test', 'account_minimal_test.xml')
        self._load('account_asset', 'test', 'account_asset_demo_test.xml')
        CEO_car = self.env['account.asset'].with_context(asset_type='purchase').create({
            'salvage_value': 0,
            'state': 'draft',
            'method_period': '12',
            'method_number': 4,
            'name': "CEO's Car",
            'original_value': 1000.0,
            'acquisition_date': fields.Date.today() - relativedelta(years=5),
            'account_asset_id': self.env.ref('account_asset.xfa').id,
            'account_depreciation_id': self.env.ref('account_asset.xfa').copy().id,
            'account_depreciation_expense_id': self.env.ref("account_asset.a_expense").id,
            'journal_id': self.env.ref('account_asset.miscellaneous_journal').id,
        })
        CEO_car.validate()
        self.assertEqual(len(CEO_car.depreciation_move_ids), 4)
        self.assertRecordValues(CEO_car, [{
            'original_value': 1000,
            'book_value': 1000,
            'value_residual': 1000,
            'salvage_value': 0,
        }])
        # post all depreciation moves
        CEO_car.depreciation_move_ids.write({'auto_post': False})
        CEO_car.depreciation_move_ids.post()
        self.assertRecordValues(CEO_car, [{
            'original_value': 1000,
            'book_value': 0,
            'value_residual': 0,
            'salvage_value': 0,
        }])
        # sell asset for a higher amount than original value
        closing_invoice = self.env['account.move'].create({
            'partner_id': self.ref("base.res_partner_12"),
            'type': 'out_invoice',
            'invoice_line_ids': [(0, 0, {'price_unit': 1500})]
        })
        closing_invoice.post()
        CEO_car.company_id.gain_account_id = self.env.ref("account_asset.a_expense").copy()
        CEO_car.set_to_close(closing_invoice.invoice_line_ids)
        closing_move = CEO_car.depreciation_move_ids.filtered(lambda l: l.state == 'draft')
        self.assertRecordValues(closing_move.line_ids, [{
            'debit': 0,
            'credit': 1000,
            'account_id': CEO_car.account_asset_id.id,
        }, {
            'debit': 1000,
            'credit': 0,
            'account_id': CEO_car.account_depreciation_id.id,
        }, {
            'debit': 1500,
            'credit': 0,
            'account_id': closing_invoice.invoice_line_ids.account_id.id,
        }, {
            'debit': 0,
            'credit': 1500,
            'account_id': CEO_car.company_id.gain_account_id.id,
        }])
        closing_move.action_post()
        self.assertRecordValues(CEO_car, [{
            'original_value': 1000,
            'book_value': 0,
            'value_residual': 0,
            'salvage_value': 0,
        }])

    def test_asset_form(self):
        """Test the form view of assets"""
        self._load('account', 'test', 'account_minimal_test.xml')
        asset_form = Form(self.env['account.asset'].with_context(asset_type='purchase'))
        asset_form.name = "Test Asset"
        asset_form.original_value = 10000
        asset_form.account_depreciation_id = self.env.ref('account_asset.xfa')
        asset_form.account_depreciation_expense_id = self.env.ref('account_asset.a_expense')
        asset_form.journal_id = self.env.ref('account_asset.miscellaneous_journal')
        asset = asset_form.save()
        asset.validate()

        # Test that the depreciations are created upon validation of the asset according to the default values
        self.assertEqual(len(asset.depreciation_move_ids), 5)
        for move in asset.depreciation_move_ids:
            self.assertEqual(move.amount_total, 2000)

        # Test that we cannot validate an asset with non zero remaining value of the last depreciation line
        asset_form = Form(asset)
        with self.assertRaises(UserError):
            with self.cr.savepoint():
                with asset_form.depreciation_move_ids.edit(4) as line_edit:
                    line_edit.amount_total = 1000.0
                asset_form.save()

        # ... but we can with a zero remaining value on the last line.
        asset_form = Form(asset)
        with asset_form.depreciation_move_ids.edit(4) as line_edit:
            line_edit.amount_total = 1000.0
        with asset_form.depreciation_move_ids.edit(3) as line_edit:
            line_edit.amount_total = 3000.0
        self.update_form_values(asset_form)
        asset_form.save()

    def test_asset_from_move_line_form(self):
        """Test that the asset is correcly created from a move line"""

        self._load('account', 'test', 'account_minimal_test.xml')

        move_ids = self.env['account.move'].create([{
            'ref': 'line1',
            'line_ids': [
                (0, 0, {
                    'account_id': self.env.ref('account_asset.a_expense').id,
                    'debit': 300,
                    'name': 'Furniture',
                }),
                (0, 0, {
                    'account_id': self.env.ref('account_asset.xfa').id,
                    'credit': 300,
                }),
            ]
        }, {
            'ref': 'line2',
            'line_ids': [
                (0, 0, {
                    'account_id': self.env.ref('account_asset.a_expense').id,
                    'debit': 600,
                    'name': 'Furniture too',
                }),
                (0, 0, {
                    'account_id': self.env.ref('account_asset.xfa').id,
                    'credit': 600,
                }),
            ]
        },
        ])
        move_ids.post()
        move_line_ids = move_ids.mapped('line_ids').filtered(lambda x: x.debit)

        asset = self.env['account.asset'].new({'original_move_line_ids': [(6, 0, move_line_ids.ids)]})
        asset_form = Form(self.env['account.asset'].with_context(default_original_move_line_ids=move_line_ids.ids, asset_type='purchase'))
        asset_form._values['original_move_line_ids'] = [(6, 0, move_line_ids.ids)]
        asset_form._perform_onchange(['original_move_line_ids'])
        asset_form.account_depreciation_expense_id = self.env.ref('account_asset.cas')

        asset = asset_form.save()
        self.assertEqual(asset.value_residual, 900.0)
        self.assertIn(asset.name, ['Furniture', 'Furniture too'])
        self.assertEqual(asset.journal_id.type, 'general')
        self.assertEqual(asset.asset_type, 'purchase')
        self.assertEqual(asset.account_asset_id, self.env.ref('account_asset.a_expense'))
        self.assertEqual(asset.account_depreciation_id, self.env.ref('account_asset.a_expense'))
        self.assertEqual(asset.account_depreciation_expense_id, self.env.ref('account_asset.cas'))

    def test_asset_modify_depreciation(self):
        """Test the modification of depreciation parameters"""
        self.env['asset.modify'].create({
            'asset_id': self.truck.id,
            'name': 'Test reason',
            'method_number': 10.0,
            "account_asset_counterpart_id": self.assert_counterpart_account_id,
        }).modify()

        # I check the proper depreciation lines created.
        self.assertEqual(10, len(self.truck.depreciation_move_ids.filtered(lambda x: x.state == 'draft')))

    def test_asset_modify_value_00(self):
        """Test the values of the asset and value increase 'assets' after a
        modification of residual and/or salvage values.
        Increase the residual value, increase the salvage value"""
        self.assertEqual(self.truck.value_residual, 3000)
        self.assertEqual(self.truck.salvage_value, 2500)

        self.env['asset.modify'].create({
            'name': 'New beautiful sticker :D',
            'asset_id': self.truck.id,
            'value_residual': 4000,
            'salvage_value': 3000,
            "account_asset_counterpart_id": self.assert_counterpart_account_id,
        }).modify()
        self.assertEqual(self.truck.value_residual, 3000)
        self.assertEqual(self.truck.salvage_value, 2500)
        self.assertEqual(self.truck.children_ids.value_residual, 1000)
        self.assertEqual(self.truck.children_ids.salvage_value, 500)

    @patch('odoo.fields.Date.today', return_value=today())
    def test_asset_modify_value_01(self, today_mock):
        "Decrease the residual value, decrease the salvage value"
        self.env['asset.modify'].create({
            'name': "Accident :'(",
            'date': fields.Date.today(),
            'asset_id': self.truck.id,
            'value_residual': 1000,
            'salvage_value': 2000,
            "account_asset_counterpart_id": self.assert_counterpart_account_id,
        }).modify()
        self.assertEqual(self.truck.value_residual, 1000)
        self.assertEqual(self.truck.salvage_value, 2000)
        self.assertEqual(self.truck.children_ids.value_residual, 0)
        self.assertEqual(self.truck.children_ids.salvage_value, 0)
        self.assertEqual(max(self.truck.depreciation_move_ids.filtered(lambda m: m.state == 'posted'), key=lambda m: m.date).amount_total, 2500)

    def test_asset_modify_value_02(self):
        "Decrease the residual value, increase the salvage value; same book value"
        self.env['asset.modify'].create({
            'name': "Don't wanna depreciate all of it",
            'asset_id': self.truck.id,
            'value_residual': 1000,
            'salvage_value': 4500,
            "account_asset_counterpart_id": self.assert_counterpart_account_id,
        }).modify()
        self.assertEqual(self.truck.value_residual, 1000)
        self.assertEqual(self.truck.salvage_value, 4500)
        self.assertEqual(self.truck.children_ids.value_residual, 0)
        self.assertEqual(self.truck.children_ids.salvage_value, 0)

    def test_asset_modify_value_03(self):
        "Decrease the residual value, increase the salvage value; increase of book value"
        self.env['asset.modify'].create({
            'name': "Some aliens did something to my truck",
            'asset_id': self.truck.id,
            'value_residual': 1000,
            'salvage_value': 6000,
            "account_asset_counterpart_id": self.assert_counterpart_account_id,
        }).modify()
        self.assertEqual(self.truck.value_residual, 1000)
        self.assertEqual(self.truck.salvage_value, 4500)
        self.assertEqual(self.truck.children_ids.value_residual, 0)
        self.assertEqual(self.truck.children_ids.salvage_value, 1500)

    def test_asset_modify_value_04(self):
        "Increase the residual value, decrease the salvage value; increase of book value"
        self.env['asset.modify'].create({
            'name': 'GODZILA IS REAL!',
            'asset_id': self.truck.id,
            'value_residual': 4000,
            'salvage_value': 2000,
            "account_asset_counterpart_id": self.assert_counterpart_account_id,
        }).modify()
        self.assertEqual(self.truck.value_residual, 3500)
        self.assertEqual(self.truck.salvage_value, 2000)
        self.assertEqual(self.truck.children_ids.value_residual, 500)
        self.assertEqual(self.truck.children_ids.salvage_value, 0)

    @patch('odoo.fields.Date.today', return_value=today())
    def test_asset_modify_report(self, today_mock):
        """Test the asset value modification flows"""
        #           PY      +   -  Final    PY     +    - Final Bookvalue
        #   -6       0  10000   0  10000     0   750    0   750      9250
        #   -5   10000      0   0  10000   750   750    0  1500      8500
        #   -4   10000      0   0  10000  1500   750    0  2250      7750
        #   -3   10000      0   0  10000  2250   750    0  3000      7000
        #   -2   10000      0   0  10000  3000   750    0  3750      6250
        #   -1   10000      0   0  10000  3750   750    0  4500      5500
        #    0   10000      0   0  10000  4500   750    0  5250      4750  <-- today
        #    1   10000      0   0  10000  5250   750    0  6000      4000
        #    2   10000      0   0  10000  6000   750    0  6750      3250
        #    3   10000      0   0  10000  6750   750    0  7500      2500

        today = fields.Date.today()

        report = self.env['account.assets.report']
        # TEST REPORT
        # look at all period, with unposted entries
        options = _init_options(report, today + relativedelta(years=-6, month=1, day=1), today + relativedelta(years=+4, month=12, day=31))
        lines = report._get_lines({**options, **{'unfold_all': False, 'all_entries': True}})
        self.assertListEqual([    0.0, 10000.0,     0.0, 10000.0,     0.0,  7500.0,     0.0,  7500.0,  2500.0],
                             [x['no_format_name'] for x in lines[0]['columns'][4:]])

        # look at all period, without unposted entries
        options = _init_options(report, today + relativedelta(years=-6, month=1, day=1), today + relativedelta(years=+4, month=12, day=31))
        lines = report._get_lines({**options, **{'unfold_all': False, 'all_entries': False}})
        self.assertListEqual([    0.0, 10000.0,     0.0, 10000.0,     0.0,  4500.0,     0.0,  4500.0,  5500.0],
                             [x['no_format_name'] for x in lines[0]['columns'][4:]])

        # look only at this period
        options = _init_options(report, today + relativedelta(years=0, month=1, day=1), today + relativedelta(years=0, month=12, day=31))
        lines = report._get_lines({**options, **{'unfold_all': False, 'all_entries': True}})
        self.assertListEqual([10000.0,     0.0,     0.0, 10000.0,  4500.0,   750.0,     0.0,  5250.0,  4750.0],
                             [x['no_format_name'] for x in lines[0]['columns'][4:]])

        # test value increase
        #           PY     +   -  Final    PY     +    - Final Bookvalue
        #   -6       0 10000   0  10000         750    0   750      9250
        #   -5   10000     0   0  10000   750   750    0  1500      8500
        #   -4   10000     0   0  10000  1500   750    0  2250      7750
        #   -3   10000     0   0  10000  2250   750    0  3000      7000
        #   -2   10000     0   0  10000  3000   750    0  3750      6250
        #   -1   10000     0   0  10000  3750   750    0  4500      5500
        #    0   10000  1500   0  11500  4500  1000    0  5500      6000  <--  today
        #    1   11500     0   0  11500  5500  1000    0  6500      5000
        #    2   11500     0   0  11500  6500  1000    0  7500      4000
        #    3   11500     0   0  11500  7500  1000    0  8500      3000
        self.assertEqual(self.truck.value_residual, 3000)
        self.assertEqual(self.truck.salvage_value, 2500)
        self.env['asset.modify'].create({
            'name': 'New beautiful sticker :D',
            'asset_id': self.truck.id,
            'value_residual': 4000,
            'salvage_value': 3000,
            "account_asset_counterpart_id": self.assert_counterpart_account_id,
        }).modify()
        self.assertEqual(self.truck.value_residual + sum(self.truck.children_ids.mapped('value_residual')), 4000)
        self.assertEqual(self.truck.salvage_value + sum(self.truck.children_ids.mapped('salvage_value')), 3000)

        # look at all period, with unposted entries
        options = _init_options(report, today + relativedelta(years=-6, month=1, day=1), today + relativedelta(years=+4, month=12, day=31))
        lines = report._get_lines({**options, **{'unfold_all': False, 'all_entries': True}})
        self.assertListEqual([    0.0, 11500.0,     0.0, 11500.0,     0.0,  8500.0,     0.0,  8500.0,  3000.0],
                             [x['no_format_name'] for x in lines[0]['columns'][4:]])

        # look only at this period
        options = _init_options(report, today + relativedelta(years=0, month=1, day=1), today + relativedelta(years=0, month=12, day=31))
        lines = report._get_lines({**options, **{'unfold_all': False, 'all_entries': True}})
        self.assertListEqual([10000.0,  1500.0,     0.0, 11500.0,  4500.0,  1000.0,     0.0,  5500.0,  6000.0],
                             [x['no_format_name'] for x in lines[0]['columns'][4:]])

        # test value decrease
        self.env['asset.modify'].create({
            'name': "Huge scratch on beautiful sticker :'( It is ruined",
            'date': fields.Date.today(),
            'asset_id': self.truck.children_ids.id,
            'value_residual': 0,
            'salvage_value': 500,
            "account_asset_counterpart_id": self.assert_counterpart_account_id,
        }).modify()
        self.env['asset.modify'].create({
            'name': "Huge scratch on beautiful sticker :'( It went through...",
            'date': fields.Date.today(),
            'asset_id': self.truck.id,
            'value_residual': 1000,
            'salvage_value': 2500,
            "account_asset_counterpart_id": self.assert_counterpart_account_id,
        }).modify()
        self.assertEqual(self.truck.value_residual + sum(self.truck.children_ids.mapped('value_residual')), 1000)
        self.assertEqual(self.truck.salvage_value + sum(self.truck.children_ids.mapped('salvage_value')), 3000)

        # look at all period, with unposted entries
        options = _init_options(report, today + relativedelta(years=-6, month=1, day=1), today + relativedelta(years=+4, month=12, day=31))
        lines = report._get_lines({**options, **{'unfold_all': False, 'all_entries': True}})
        self.assertListEqual([    0.0, 11500.0,     0.0, 11500.0,     0.0,  8500.0,     0.0,  8500.0,  3000.0],
                             [x['no_format_name'] for x in lines[0]['columns'][4:]])

        # look only at this period
        options = _init_options(report, today + relativedelta(years=0, month=1, day=1), today + relativedelta(years=0, month=12, day=31))
        lines = report._get_lines({**options, **{'unfold_all': False, 'all_entries': True}})
        self.assertListEqual([10000.0,  1500.0,     0.0, 11500.0,  4500.0,  3250.0,     0.0,  7750.0,  3750.0],
                             [x['no_format_name'] for x in lines[0]['columns'][4:]])

    def test_asset_reverse_depreciation(self):
        """Test the reversal of a depreciation move"""
        self._load('account', 'test', 'account_minimal_test.xml')

        self.assertEqual(sum(self.truck.depreciation_move_ids.filtered(lambda m: m.state == 'posted').mapped('amount_total')), 4500)
        self.assertEqual(sum(self.truck.depreciation_move_ids.filtered(lambda m: m.state == 'draft').mapped('amount_total')), 3000)
        self.assertEqual(max(self.truck.depreciation_move_ids.filtered(lambda m: m.state == 'posted'), key=lambda m: m.date).asset_remaining_value, 3000)

        move_to_reverse = self.truck.depreciation_move_ids.filtered(lambda m: m.state == 'posted')[-1]
        move_to_reverse._reverse_moves()

        # Check that we removed the depreciation in the table for the reversed move
        max_date_posted_before = max(self.truck.depreciation_move_ids.filtered(lambda m: m.state == 'posted' and m.date < move_to_reverse.date), key=lambda m: m.date)
        self.assertEqual(move_to_reverse.asset_remaining_value, max_date_posted_before.asset_remaining_value)
        self.assertEqual(move_to_reverse.asset_depreciated_value, max_date_posted_before.asset_depreciated_value)

        # Check that the depreciation has been reported on the next move
        min_date_draft = min(self.truck.depreciation_move_ids.filtered(lambda m: m.state == 'draft' and m.date > move_to_reverse.date), key=lambda m: m.date)
        self.assertEqual(move_to_reverse.asset_remaining_value - min_date_draft.amount_total, min_date_draft.asset_remaining_value)
        self.assertEqual(move_to_reverse.asset_depreciated_value + min_date_draft.amount_total, min_date_draft.asset_depreciated_value)

        # The amount is still there, it only has been reversed. But it has been added on the next draft move to complete the depreciation table
        self.assertEqual(sum(self.truck.depreciation_move_ids.filtered(lambda m: m.state == 'posted').mapped('amount_total')), 4500)
        self.assertEqual(sum(self.truck.depreciation_move_ids.filtered(lambda m: m.state == 'draft').mapped('amount_total')), 3750)

        # Check that the table shows fully depreciated at the end
        self.assertEqual(self.truck.depreciation_move_ids[-1].asset_remaining_value, 0)
        self.assertEqual(self.truck.depreciation_move_ids[-1].asset_depreciated_value, 7500)

    def test_asset_reverse_original_move(self):
        """Test the reversal of a move that generated an asset"""
        self._load('account', 'test', 'account_minimal_test.xml')

        move_id = self.env['account.move'].create({
            'ref': 'line1',
            'line_ids': [
                (0, 0, {
                    'account_id': self.env.ref('account_asset.a_expense').id,
                    'debit': 300,
                    'name': 'Furniture',
                }),
                (0, 0, {
                    'account_id': self.env.ref('account_asset.xfa').id,
                    'credit': 300,
                }),
            ]
        })
        move_id.post()
        move_line_id = move_id.mapped('line_ids').filtered(lambda x: x.debit)

        asset_form = Form(self.env['account.asset'].with_context(asset_type='purchase'))
        asset_form._values['original_move_line_ids'] = [(6, 0, move_line_id.ids)]
        asset_form._perform_onchange(['original_move_line_ids'])
        asset_form.account_depreciation_expense_id = self.env.ref('account_asset.cas')

        asset = asset_form.save()

        self.assertTrue(asset.name, 'An asset should have been created')
        reversed_move_id = move_id._reverse_moves()
        reversed_move_id.post()
        with self.assertRaises(MissingError, msg='The asset should have been deleted'):
            asset.name

    def test_asset_credit_note(self):
        """Test the generated entries created from an in_refund invoice with deferred expense."""
        self._load('account_asset', 'test', 'account_asset_demo_test.xml')
        a_asset = self.browse_ref("account_asset.a_expense")
        asset_model = self.browse_ref("account_asset.account_asset_model_fixedassets_test0")
        a_asset.create_asset = 'validate'
        a_asset.asset_model = asset_model
        a_asset.user_type_id = self.env.ref('account.data_account_type_current_assets').id
        asset_model.journal_id = self.env.ref('account_asset.miscellaneous_journal').id
        asset_model.prorata = False
        asset_model.asset_type = 'expense'

        invoice = self.env['account.move'].create({
            'type': 'in_refund',
            'partner_id': self.ref("base.res_partner_12"),
            'invoice_line_ids': [(0, 0, {
                'name': 'Refund Insurance claim',
                'account_id': a_asset.id,
                'price_unit': 450,
                'quantity': 1,
            })],
        })
        invoice.post()
        depreciation_lines = self.env['account.move.line'].search([
            ('account_id', '=', asset_model.account_depreciation_id.id),
            ('move_id.asset_id', '=', invoice.asset_ids.id),
            ('debit', '=', 150),
        ])
        self.assertEqual(
            len(depreciation_lines), 3,
            'Three entries with a debit of 150 must be created on the Deferred Expense Account'
        )

    def test_asset_partial_credit_note(self):
        """Test partial credit note on an in invoice that has generated draft deferred revenue."""
        self._load('account_asset', 'test', 'account_deferred_revenue_demo_test.xml')
        a_asset = self.browse_ref("account_asset.a_sale")
        asset_model = self.browse_ref("account_asset.account_asset_model_sale_test0")
        a_asset.create_asset = 'draft'
        a_asset.asset_model = asset_model
        a_asset.user_type_id = self.env.ref('account.data_account_type_current_liabilities').id
        asset_model.journal_id = self.env.ref('account_asset.miscellaneous_journal').id
        asset_model.prorata = False
        asset_model.asset_type = 'sale'

        product_a = self.env['product.product'].create({
            'name': 'Product A',
            'default_code': 'PA',
            'lst_price': 100.0,
            'standard_price': 100.0,
        })
        product_b = self.env['product.product'].create({
            'name': 'Product B',
            'default_code': 'PB',
            'lst_price': 200.0,
            'standard_price': 200.0,
        })
        invoice = self.env['account.move'].create({
            'type': 'in_invoice',
            'partner_id': self.ref("base.res_partner_12"),
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': product_a,
                    'name': 'Product A',
                    'account_id': a_asset.id,
                    'price_unit': product_a.lst_price,
                    'quantity': 4,
                }),
                (0, 0, {
                    'product_id': product_b,
                    'name': 'Product B',
                    'account_id': a_asset.id,
                    'price_unit': product_b.lst_price,
                    'quantity': 5,
                }),
                (0, 0, {
                    'product_id': product_a,
                    'name': 'Product A',
                    'account_id': a_asset.id,
                    'price_unit': product_a.lst_price,
                    'quantity': 6,
                }),
            ],
        })
        invoice.post()
        self.assertEqual(
            invoice.line_ids.filtered(lambda l: l.asset_id).mapped(lambda l: (l.product_id, l.quantity)),
            [(product_a, 4), (product_b, 5), (product_a, 6)]
        )
        move_reversal = self.env['account.move.reversal'].with_context(active_model="account.move", active_ids=invoice.ids).create({
            'date': fields.Date.from_string('2019-02-01'),
            'reason': 'no reason',
            'refund_method': 'refund',
        })
        reversal = move_reversal.reverse_moves()
        credit_note = self.env['account.move'].browse(reversal['res_id'])
        with Form(credit_note) as move_form:
            move_form.invoice_line_ids.remove(0)
        credit_note.post()
        self.assertEqual(
            invoice.line_ids.filtered(lambda l: l.asset_id).mapped(lambda l: (l.product_id, l.quantity)),
            [(product_a, 4)]
        )

    def test_post_asset_with_passed_recognition_date(self):
        """
        Check the state of an asset when the last recognition date
        is passed at the moment of posting it.
        """
        asset = self.env['account.asset'].create({
            'account_asset_id': self.env.ref('account_asset.a_expense').id,
            'account_depreciation_id': self.env.ref('account_asset.a_expense').id,
            'account_depreciation_expense_id': self.env.ref('account_asset.cas').id,
            'journal_id': self.env.ref('account_asset.miscellaneous_journal').id,
            'asset_type': 'expense',
            'name': 'test',
            'acquisition_date': today() - relativedelta(years=1, month=6, day=1),
            'original_value': 10000,
            'method_number': 5,
            'method_period': '1',
            'method': 'linear',
        })
        asset.validate()
        self.env['account.move']._autopost_draft_entries()

        self.assertTrue(all(m.state == 'posted' for m in asset.depreciation_move_ids))
        self.assertEqual(asset.state, 'close')

    @freeze_time('2022-08-25')
    def test_decrement_book_value_with_negative_asset(self):
        """
        Test the computation of book value and remaining value
        when posting a depreciation move related with a negative asset
        """
        depreciation_account = self.env.ref('account_asset.a_expense')
        asset_model = self.env['account.asset'].create({
            'name': 'test',
            'state': 'model',
            'active': True,
            'asset_type': 'purchase',
            'method': 'linear',
            'method_number': 5,
            'method_period': '1',
            'prorata': False,
            'account_asset_id': depreciation_account.id,
            'account_depreciation_id': depreciation_account.id,
            'account_depreciation_expense_id': self.env.ref('account_asset.cas').id,
            'journal_id': self.env.ref('account_asset.miscellaneous_journal').id,
        })

        depreciation_account.asset_type = 'purchase'
        depreciation_account.can_create_asset = True
        depreciation_account.create_asset = 'draft'
        depreciation_account.asset_model = asset_model

        refund = self.env['account.move'].create({
            'type': 'in_refund',
            'partner_id': self.ref("base.res_partner_12"),
            'invoice_date': today() - relativedelta(months=1),
            'invoice_line_ids': [(0, 0, {'name': 'refund', 'account_id': depreciation_account.id, 'price_unit': 500})],
        })
        refund.post()

        self.assertTrue(refund.asset_ids)

        asset = refund.asset_ids
        asset.validate()

        self.assertEqual(asset.book_value, refund.amount_total)
        self.assertEqual(asset.value_residual, refund.amount_total)

        self.env['account.move']._autopost_draft_entries()

        self.assertEqual(len(asset.depreciation_move_ids.filtered(lambda m: m.state == 'posted')), 1)
        self.assertEqual(asset.book_value, 400.0)
        self.assertEqual(asset.value_residual, 400.0)
