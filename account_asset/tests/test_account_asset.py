# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import tools
from odoo.tests import common
from odoo.modules.module import get_resource_path


class TestAccountAsset(common.TransactionCase):

    def _load(self, module, *args):
        tools.convert_file(self.cr, 'account_asset',
                           get_resource_path(module, *args),
                           {}, 'init', False, 'test', self.registry._assertion_report)

    def test_00_account_asset_asset(self):
        self._load('account', 'test', 'account_minimal_test.xml')
        self._load('account_asset', 'test', 'account_asset_demo_test.xml')

        # In order to test the process of Account Asset, I perform a action to confirm Account Asset.
        self.browse_ref("account_asset.account_asset_asset_vehicles_test0").validate()

        # I check Asset is now in Open state.
        self.assertEqual(self.browse_ref("account_asset.account_asset_asset_vehicles_test0").state, 'open',
            'Asset should be in Open state')

        # I compute depreciation lines for asset of CEOs Car.
        self.browse_ref("account_asset.account_asset_asset_vehicles_test0").compute_depreciation_board()
        value = self.browse_ref("account_asset.account_asset_asset_vehicles_test0")
        self.assertEqual(value.method_number, len(value.depreciation_line_ids),
            'Depreciation lines not created correctly')
        # 10k over 5 years, linear, no prorata -> 2000 / year
        self.assertEqual(2000, value.depreciation_line_ids[0].amount)

        # I create account move for all depreciation lines.
        ids = self.env['account.asset.depreciation.line'].search([('asset_id', '=', self.ref('account_asset.account_asset_asset_vehicles_test0'))])
        for line in ids:
            line.create_move()

        # I check the move line is created.
        asset = self.env['account.asset.asset'].browse([self.ref("account_asset.account_asset_asset_vehicles_test0")])[0]
        self.assertEqual(len(asset.depreciation_line_ids), asset.entry_count,
            'Move lines not created correctly')

        # I Check that After creating all the moves of depreciation lines the state "Close".
        self.assertEqual(self.browse_ref("account_asset.account_asset_asset_vehicles_test0").state, 'close',
            'State of asset should be close')

        # WIZARD
        # I create a record to change the duration of asset for calculating depreciation.
        account_asset_asset_office0 = self.browse_ref('account_asset.account_asset_asset_office_test0')
        asset_modify_number_0 = self.env['asset.modify'].with_context({
            'active_id': account_asset_asset_office0.id
        }).create({
            'name': 'Test reason',
            'method_number': 10.0,
        })
        # I change the duration.
        asset_modify_number_0.with_context({'active_id': account_asset_asset_office0.id}).modify()

        # I check the proper depreciation lines created.
        self.assertEqual(account_asset_asset_office0.method_number, len(account_asset_asset_office0.depreciation_line_ids))
        # I compute a asset on period.
        context = {
            "active_ids": [self.ref("account_asset.menu_asset_depreciation_confirmation_wizard")],
            "active_id": self.ref('account_asset.menu_asset_depreciation_confirmation_wizard'),
            'type': 'sale'
        }
        asset_compute_period_0 = self.env['asset.depreciation.confirmation.wizard'].create({})
        asset_compute_period_0.with_context(context).asset_compute()

    def test_asset_depreciation_degressive(self):
        """
        Degressive depreciation with a 1 month period
        """
        self._load('account', 'test', 'account_minimal_test.xml')
        self._load('account_asset', 'test', 'account_asset_demo_test.xml')

        # In order to test the process of Account Asset, I perform a action to confirm Account Asset.
        value = self.browse_ref("account_asset.account_asset_asset_vehicles_test0")
        value.method = 'degressive'
        value.method_number = 5
        value.method_period = 1
        value.method_progress_factor = .3
        value.prorata = False
        value.value = 1100
        value.salvage_value = 100
        value.validate()

        # I compute depreciation lines for asset of CEOs Car.
        self.browse_ref("account_asset.account_asset_asset_vehicles_test0").compute_depreciation_board()
        self.assertEqual(value.method_number, len(value.depreciation_line_ids),
            'Depreciation lines not created correctly')
        dep_lines = value.depreciation_line_ids.sorted('depreciation_date')
        self.assertEqual(300, dep_lines[0].amount)
        self.assertEqual(210, dep_lines[1].amount)
        self.assertEqual(147, dep_lines[2].amount)
        self.assertEqual(102.90, dep_lines[3].amount)
        self.assertEqual(240.10, dep_lines[4].amount)

    def test_asset_depreciation_first_period_too_large(self):
        """
        Linear depreciation with a 1 month period. 
        If the first depreciation date is placed such that the first period is
        over a month, we still do the depreciation based on a half-month period
        (standard behavior of Odoo v12-14)
        """
        self._load('account', 'test', 'account_minimal_test.xml')
        self._load('account_asset', 'test', 'account_asset_demo_test.xml')

        # In order to test the process of Account Asset, I perform a action to confirm Account Asset.
        value = self.browse_ref("account_asset.account_asset_asset_vehicles_test0")
        value.method = 'linear'
        value.method_number = 10
        value.method_period = 1
        value.date_first_depreciation = 'manual'
        value.first_depreciation_manual_date = '2020-12-31'
        value.date = '2020-11-15'
        value.prorata = True
        value.value = 1100
        value.salvage_value = 100
        value.validate()

        # I compute depreciation lines for asset of CEOs Car.
        self.browse_ref("account_asset.account_asset_asset_vehicles_test0").compute_depreciation_board()
        self.assertEqual(value.method_number + 1, len(value.depreciation_line_ids),
            'Depreciation lines not created correctly')
        dep_lines = value.depreciation_line_ids.sorted('depreciation_date')
        self.assertEqual(53.33, round(dep_lines[0].amount, 2), 
            'Calculate based on a half month (even though in fact there was a full month)')
        self.assertEqual(100, dep_lines[1].amount)

    def test_asset_depreciation_prorated_multimonths(self):
        """
        If you have an asset depreciated over a period of time every 3 month, with prorated depreciation, the depreciation for the 
        first period should be calculated based on the period length (not 1 month)
        """
        self._load('account', 'test', 'account_minimal_test.xml')
        self._load('account_asset', 'test', 'account_asset_demo_test.xml')

        # In order to test the process of Account Asset, I perform a action to confirm Account Asset.
        value = self.browse_ref("account_asset.account_asset_asset_vehicles_test0")
        value.method = 'linear'
        value.date_first_depreciation = 'manual'
        value.first_depreciation_manual_date = '2020-12-31'
        value.date = '2020-11-20'
        value.method_number = 12
        value.method_period = 3
        value.prorata = True
        value.value = 14000
        value.salvage_value = 2000
        value.validate()
        value.compute_depreciation_board()
        self.assertEqual(value.method_number + 1, len(value.depreciation_line_ids),
            'Depreciation lines not created correctly (we have one extra, because prorata)')
        dep_lines = value.depreciation_line_ids.sorted('depreciation_date')
        # 31 + 11 days out of 31 + 31 + 30 days
        self.assertEqual(456.52, round(dep_lines[0].amount, 2), 'first entry should be prorated: 1000 but only 1 month + 2 weeks out of the 3 month, so 500')
        self.assertEqual(1000, round(dep_lines[1].amount, 2), 'second entry should be for the full amount')
        self.assertEqual(1000 - 456.52, round(dep_lines[-1].amount, 2), 'last entry should be for the balance')
        self.assertEqual(12000, round(sum(dep_lines.mapped('amount')), 2), 'total depreciated should match original value')

    def test_asset_depreciation_prorated_multimonths_1day(self):
        """
        Edge case: just 1 day
        """
        self._load('account', 'test', 'account_minimal_test.xml')
        self._load('account_asset', 'test', 'account_asset_demo_test.xml')

        # In order to test the process of Account Asset, I perform a action to confirm Account Asset.
        value = self.browse_ref("account_asset.account_asset_asset_vehicles_test0")
        value.method = 'linear'
        value.date_first_depreciation = 'manual'
        value.first_depreciation_manual_date = '2020-12-31'
        value.date = '2020-12-31'
        value.method_number = 12
        value.method_period = 3
        value.prorata = True
        value.value = 14000
        value.salvage_value = 2000
        value.validate()
        value.compute_depreciation_board()
        dep_lines = value.depreciation_line_ids.sorted('depreciation_date')
        self.assertEqual(10.87, round(dep_lines[0].amount, 2), 'first entry should be prorated')

    def test_asset_depreciation_prorated_multimonths_fullperiod(self):
        """
        Edge case: 3 months
        """
        self._load('account', 'test', 'account_minimal_test.xml')
        self._load('account_asset', 'test', 'account_asset_demo_test.xml')

        # In order to test the process of Account Asset, I perform a action to confirm Account Asset.
        value = self.browse_ref("account_asset.account_asset_asset_vehicles_test0")
        value.method = 'linear'
        value.date_first_depreciation = 'manual'
        value.first_depreciation_manual_date = '2020-12-31'
        value.date = '2020-10-01'
        value.method_number = 12
        value.method_period = 3
        value.prorata = True
        value.value = 14000
        value.salvage_value = 2000
        value.validate()
        value.compute_depreciation_board()
        dep_lines = value.depreciation_line_ids.sorted('depreciation_date')
        self.assertEqual(1000, round(dep_lines[0].amount, 2), 'first entry should be prorated')

    def test_asset_depreciation_prorated_multimonths_invalid_first_period(self):
        """
        If the first depreciation period is over the length of a normal depreciation
        period, we should still max out at the nominal depreciation per period amount
        """
        self._load('account', 'test', 'account_minimal_test.xml')
        self._load('account_asset', 'test', 'account_asset_demo_test.xml')

        # In order to test the process of Account Asset, I perform a action to confirm Account Asset.
        value = self.browse_ref("account_asset.account_asset_asset_vehicles_test0")
        value.method = 'linear'
        value.date_first_depreciation = 'manual'
        value.first_depreciation_manual_date = '2021-12-31'
        value.date = '2020-11-15'
        value.method_number = 12
        value.method_period = 3
        value.prorata = True
        value.value = 14000
        value.salvage_value = 2000
        value.validate()
        value.compute_depreciation_board()
        self.assertEqual(value.method_number, len(value.depreciation_line_ids),
            'Depreciation lines not created correctly (no extra here since first prorated period is botched)')
        dep_lines = value.depreciation_line_ids.sorted('depreciation_date')
        self.assertEqual(1000, round(dep_lines[0].amount, 2), 'first entry should be capped at full amount')
        self.assertEqual(12000, round(sum(dep_lines.mapped('amount')), 2), 'total depreciated should match original value')


    def test_asset_depreciation_method_number_invalid_method_number(self):
        """
        Make sure we don't blow up if there is invalid input
        """
        self._load('account', 'test', 'account_minimal_test.xml')
        self._load('account_asset', 'test', 'account_asset_demo_test.xml')

        # In order to test the process of Account Asset, I perform a action to confirm Account Asset.
        value = self.browse_ref("account_asset.account_asset_asset_vehicles_test0")
        value.method = 'linear'
        value.date_first_depreciation = 'manual'
        value.first_depreciation_manual_date = '2020-12-31'
        value.date = '2020-11-15'
        value.method_number = 0
        value.method_period = 3
        value.prorata = True
        value.value = 14000
        value.salvage_value = 2000
        value.validate()
        value.compute_depreciation_board()
        self.assertEqual(value.method_number + 1, len(value.depreciation_line_ids))
        dep_lines = value.depreciation_line_ids.sorted('depreciation_date')
        self.assertEqual(12000, round(dep_lines[0].amount, 2), 'first entry should have everything, since we have 0 method number')

    def test_asset_depreciation_prorated_multimonth_degressive(self):
        """
        If you have an asset depreciated over a period of time every 3 month, with prorated depreciation, the depreciation for the 
        first period should be calculated based on the period length (not 1 month)
        """
        self._load('account', 'test', 'account_minimal_test.xml')
        self._load('account_asset', 'test', 'account_asset_demo_test.xml')

        # In order to test the process of Account Asset, I perform a action to confirm Account Asset.
        value = self.browse_ref("account_asset.account_asset_asset_vehicles_test0")
        value.method = 'degressive'
        value.method_progress_factor = .3
        value.date_first_depreciation = 'manual'
        value.first_depreciation_manual_date = '2020-12-31'
        value.date = '2020-11-20'
        value.method_number = 12
        value.method_period = 3
        value.prorata = True
        value.value = 14000
        value.salvage_value = 2000
        value.validate()
        value.compute_depreciation_board()
        self.assertEqual(value.method_number + 1, len(value.depreciation_line_ids),
            'Depreciation lines not created correctly (we have one extra, because prorata)')
        dep_lines = value.depreciation_line_ids.sorted('depreciation_date')
        self.assertEqual(1643.48, round(dep_lines[0].amount, 2), 'first entry should be prorated: 3600 but only 1.25 month, so 1800')
        self.assertEqual(3106.96, round(dep_lines[1].amount, 2), 'second entry should be for the full amount (taking into account the 1643 that was already depreciated)')
        self.assertEqual(12000, round(sum(dep_lines.mapped('amount')), 2), 'total depreciated amount should match')

    def test_asset_depreciation_prorated_multiyear(self):
        """
        If you have an asset depreciated over a period of time every 3 year, with prorated depreciation, the depreciation for the 
        first period should be calculated based on the period length (not 1 year)
        """
        self._load('account', 'test', 'account_minimal_test.xml')
        self._load('account_asset', 'test', 'account_asset_demo_test.xml')

        # In order to test the process of Account Asset, I perform a action to confirm Account Asset.
        value = self.browse_ref("account_asset.account_asset_asset_vehicles_test0")
        value.method = 'linear'
        value.date_first_depreciation = 'manual'
        value.first_depreciation_manual_date = '2020-12-31'
        value.date = '2020-11-15'
        value.method_number = 12
        value.method_period = 36
        value.prorata = True
        value.value = 14000
        value.salvage_value = 2000
        value.validate()
        value.compute_depreciation_board()
        self.assertEqual(value.method_number + 1, len(value.depreciation_line_ids),
            'Depreciation lines not created correctly (we have one extra, because prorata)')
        dep_lines = value.depreciation_line_ids.sorted('depreciation_date')
        # out of a period of 366 + 365 + 365 days, we have a first period of only 31 + 16 days
        self.assertEqual(42.88, round(dep_lines[0].amount, 2), 
            'first entry should be prorated: 1000 but only 2 year + 11 month + 2 weeks out of the 3 year')
        self.assertEqual(1000, round(dep_lines[1].amount, 2), 
            'second entry should be for the full amount')
        self.assertEqual(12000, round(sum(dep_lines.mapped('amount')), 2), 
            'total depreciated amount should match')