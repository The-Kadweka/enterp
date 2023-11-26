# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import base64

from odoo.exceptions import UserError
from odoo.addons.account.tests.account_test_savepoint import AccountTestInvoicingCommon
from odoo.modules.module import get_module_resource
from odoo.addons.account_bank_statement_import_camt.wizard.account_bank_statement_import_camt import _logger as camt_wizard_logger


NORMAL_AMOUNTS = [100, 150, 250]
LARGE_AMOUNTS = [10000, 15000, 25000]

class TestCamtFile(AccountTestInvoicingCommon):

    """ Tests for import bank statement CAMT file format (account.bank.statement.import) """
    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        # Setup a partner with the same bank accounts found in the camt file
        cls.partner_id = cls.env['res.partner'].create({'name': 'Foo'})
        cls.env['res.partner.bank'].create({
            'acc_number': '10987654322',
            'partner_id': cls.partner_id.id
        })
        cls.env['res.partner.bank'].create({
            'acc_number': 'BE68539007547034',
            'partner_id': cls.partner_id.id
        })
        cls.eur_company = cls.env['res.company'].create({'name': "SuperCompany EUR", 'currency_id': cls.env.ref('base.EUR').id})
        cls.usd_company = cls.env['res.company'].create({'name': "SuperCompany USD", 'currency_id': cls.env.ref('base.USD').id})

    def test_camt_file_import(self):
        # Get CAMT file content
        camt_file_path = get_module_resource('account_bank_statement_import_camt', 'test_camt_file', 'test_camt.xml')
        camt_file = base64.b64encode(open(camt_file_path, 'rb').read())

        # Create a bank account and journal corresponding to the CAMT file (same currency and account number)
        bank_journal = self.env['account.journal'].create({'name': 'Bank 123456', 'code': 'BNK67', 'type': 'bank',
                                                              'bank_acc_number': '123456'})
        bank_journal_id = bank_journal.id
        if bank_journal.company_id.currency_id != self.env.ref("base.USD"):
            bank_journal.write({'currency_id': self.env.ref("base.USD").id})

        # Use an import wizard to process the file
        self.env['account.bank.statement.import'].with_context(journal_id=bank_journal.id).create({'attachment_ids': [(0, 0, {
            'name': 'test file',
            'datas': camt_file,
        })]}).import_file()

        # Check the imported bank statement
        bank_st_record = self.env['account.bank.statement'].search([('name', '=', '0574908765.2015-12-05')], limit=1)
        self.assertEqual(bank_st_record.balance_start, 8998.20, "Start balance not matched.")
        self.assertAlmostEqual(bank_st_record.balance_end_real, 2661.49, 2, "End balance not matched.")

        # Check an imported bank statement line
        line = bank_st_record.line_ids.filtered(lambda r: r.ref == 'INNDNL2U20150105000217200000708')
        self.assertEqual(line.partner_name, 'Deco Addict')
        self.assertEqual(line.amount, 1636.88)
        self.assertEqual(line.partner_id.id, self.partner_id.id)

    def test_minimal_camt_file_import(self):
        """
        This basic test aims at importing a file with amounts expressed in USD
        while the company's currency is USD too and the journal has not any currency
        """
        usd_currency = self.env.ref('base.USD')
        self.env.user.write({'company_id': self.usd_company.id})
        self._test_minimal_camt_file_import('camt_053_minimal.xml', usd_currency)

    def test_minimal_and_multicurrency_camt_file_import(self):
        """
        This test aims at importing a file with amounts expressed in EUR and USD.
        The company's currency is USD.
        """
        usd_currency = self.env.ref('base.USD')
        self.env.user.write({'company_id': self.usd_company.id})
        self._test_minimal_camt_file_import('camt_053_minimal_and_multicurrency.xml', usd_currency)

    def test_minimal_and_multicurrency_camt_file_import_02(self):
        """
        This test aims at importing a file with amounts expressed in EUR and USD.
        The company's currency is USD.
        The exchange rate is provided and the company's currency is set in the source currency.
        """
        usd_currency = self.env.ref('base.USD')
        self.env.user.write({'company_id': self.usd_company.id})
        self._test_minimal_camt_file_import('camt_053_minimal_and_multicurrency_02.xml', usd_currency)

    def test_minimal_and_multicurrency_camt_file_import_03(self):
        """
        This test aims at importing a file with amounts expressed in EUR and USD but with no rate provided.
        The company's currency is USD.
        """
        usd_currency = self.env.ref('base.USD')
        self.env.user.write({'company_id': self.usd_company.id})
        self._test_minimal_camt_file_import('camt_053_minimal_and_multicurrency_03.xml', usd_currency)

    def test_minimal_and_multicurrency_camt_file_import_04(self):
        """
        This test aims at importing a file with amounts expressed in EUR and USD.
        The company's currency is USD.
        This is the same test than test_minimal_and_multicurrency_camt_file_import_02,
        except that the company's currency is set in the target currency.
        """
        usd_currency = self.env.ref('base.USD')
        self.env.user.write({'company_id': self.usd_company.id})
        self._test_minimal_camt_file_import('camt_053_minimal_and_multicurrency_04.xml', usd_currency)

    def test_minimal_and_multicurrency_camt_file_import_05(self):
        """
        This test aims at importing a file with amounts expressed in EUR and USD.
        The company's currency is USD.
        This is the same test than test_minimal_and_multicurrency_camt_file_import_04,
        except that the exchange rate is inverted.
        """
        usd_currency = self.env.ref('base.USD')
        self.env.user.write({'company_id': self.usd_company.id})
        self._test_minimal_camt_file_import('camt_053_minimal_and_multicurrency_05.xml', usd_currency)

    def test_minimal_and_multicurrency_camt_file_import_06(self):
        """
        This test aims at importing a file with amounts expressed in EUR and USD.
        The company's currency is USD.
        This is the same test than test_minimal_and_multicurrency_camt_file_import_02,
        except that the exchange rate is leading to a rounding difference.
        """
        usd_currency = self.env.ref('base.USD')
        self.env.user.write({'company_id': self.usd_company.id})
        self._test_minimal_camt_file_import('camt_053_minimal_and_multicurrency_06.xml', usd_currency)

    def test_minimal_and_multicurrency_camt_file_import_07(self):
        """
        This test aims at importing a file with amounts expressed in EUR and USD.
        The company's currency is USD.
        This is the same test than test_minimal_and_multicurrency_camt_file_import,
        except that the exchange rate is rounded to 4 digits.
        """
        usd_currency = self.env.ref('base.USD')
        self.env.user.write({'company_id': self.usd_company.id})
        self._test_minimal_camt_file_import('camt_053_minimal_and_multicurrency_07.xml', usd_currency)

    def test_several_minimal_stmt_different_currency(self):
        """
        Two different journals with the same bank account. The first one is in USD, the second one in EUR
        Test to import a CAMT file with two statements: one in USD, another in EUR
        """
        usd_currency = self.env.ref('base.USD')
        eur_currency = self.env.ref('base.EUR')
        self.env.user.write({'company_id': self.usd_company.id})
        # USD Statement
        self._test_minimal_camt_file_import('camt_053_several_minimal_stmt_different_currency.xml', usd_currency)
        # EUR Statement
        self._test_minimal_camt_file_import('camt_053_several_minimal_stmt_different_currency.xml', eur_currency,
                                            start_balance=2000, end_balance=3000)

    def test_journal_with_other_currency(self):
        """
        This test aims at importing a file with amounts expressed in USD into a journal
        that also uses USD while the company's currency is EUR.
        """
        usd_currency = self.env.ref('base.USD')
        self.env.user.write({'company_id': self.eur_company.id})
        self._test_minimal_camt_file_import('camt_053_minimal.xml', usd_currency)

    def _import_camt_file(self, camt_file_name, currency):
        # Create a bank account and journal corresponding to the CAMT
        # file (same currency and account number)
        BankAccount = self.env['res.partner.bank']
        partner = self.env.user.company_id.partner_id
        bank_account = BankAccount.search([('acc_number', '=', '112233'), ('partner_id', '=', partner.id)]) \
                       or BankAccount.create({'acc_number': '112233', 'partner_id': partner.id})
        bank_journal = self.env['account.journal'].create(
            {
                'name': "Bank 112233 %s" % currency.name,
                'code': 'BNK68',
                'type': 'bank',
                'bank_account_id': bank_account.id,
                'currency_id': currency.id,
            }
        )

        # Use an import wizard to process the file
        camt_file_path = get_module_resource(
            'account_bank_statement_import_camt',
            'test_camt_file',
            camt_file_name,
        )
        with open(camt_file_path, 'rb') as fd:
            camt_file = base64.b64encode(fd.read())
        self.env['account.bank.statement.import'].with_context(journal_id=bank_journal.id).create({'attachment_ids': [(0, 0, {
            'name': 'test file',
            'datas': camt_file,
        })]}).import_file()

    def _test_minimal_camt_file_import(self, camt_file_name, currency, start_balance=1000, end_balance=1500):
        # Create a bank account and journal corresponding to the CAMT
        # file (same currency and account number)
        self._import_camt_file(camt_file_name, currency)
        # Check the imported bank statement
        bank_st_record = self.env['account.bank.statement'].search(
            [('name', '=', '2514988305.2019-02-13')]
        ).filtered(lambda bk_stmt: bk_stmt.currency_id == currency).ensure_one()
        self.assertEqual(
            bank_st_record.balance_start, start_balance, "Start balance not matched"
        )
        self.assertEqual(
            bank_st_record.balance_end_real, end_balance, "End balance not matched"
        )

        # Check the imported bank statement line
        line = bank_st_record.line_ids.ensure_one()
        self.assertEqual(line.amount, end_balance - start_balance, "Transaction not matched")

    def _test_camt_with_several_tx_details(self, filename, expected_amounts=None):
        if expected_amounts is None:
            expected_amounts = NORMAL_AMOUNTS
        usd_currency = self.env.ref('base.USD')
        self.env.user.write({'company_id': self.usd_company.id})
        self._import_camt_file(filename, usd_currency)
        imported_statement = self.env['account.bank.statement'].search([('company_id', '=', self.usd_company.id)], order='id desc', limit=1)
        self.assertEqual(len(imported_statement.line_ids), 3)
        self.assertEqual(imported_statement.line_ids[0].name, 'label01')
        self.assertEqual(imported_statement.line_ids[0].amount, expected_amounts[0])
        self.assertEqual(imported_statement.line_ids[1].name, 'label02')
        self.assertEqual(imported_statement.line_ids[1].amount, expected_amounts[1])
        self.assertEqual(imported_statement.line_ids[2].name, 'label03')
        self.assertEqual(imported_statement.line_ids[2].amount, expected_amounts[2])

    def test_camt_with_several_tx_details(self):
        self._test_camt_with_several_tx_details('camt_053_several_tx_details.xml')

    def test_camt_with_several_tx_details_and_instructed_amount(self):
        self._test_camt_with_several_tx_details('camt_053_several_tx_details_and_instructed_amount.xml')

    def test_camt_with_several_tx_details_and_instructed_amount_02(self):
        self._test_camt_with_several_tx_details('camt_053_several_tx_details_and_instructed_amount_02.xml')

    def test_camt_with_several_tx_details_and_multicurrency_01(self):
        self._test_camt_with_several_tx_details('camt_053_several_tx_details_and_multicurrency_01.xml')

    def test_camt_with_several_tx_details_and_multicurrency_02(self):
        self._test_camt_with_several_tx_details('camt_053_several_tx_details_and_multicurrency_02.xml')

    def test_camt_with_several_tx_details_and_multicurrency_03(self):
        self._test_camt_with_several_tx_details('camt_053_several_tx_details_and_multicurrency_03.xml')

    def test_camt_with_several_tx_details_and_multicurrency_04(self):
        self._test_camt_with_several_tx_details('camt_053_several_tx_details_and_multicurrency_04.xml',
            expected_amounts=LARGE_AMOUNTS)

    def test_camt_with_several_tx_details_and_charges(self):
        self._test_camt_with_several_tx_details('camt_053_several_tx_details_and_charges.xml')

    def test_several_ibans_match_journal_camt_file_import(self):
        # Create a bank account and journal corresponding to the CAMT
        # file (same currency and account number)
        bank_journal = self.env['account.journal'].create(
            {
                'name': "Bank BE86 6635 9439 7150",
                'code': 'BNK69',
                'type': 'bank',
                'bank_acc_number': 'BE86 6635 9439 7150',
            }
        )
        if bank_journal.company_id.currency_id != self.env.ref('base.USD'):
            bank_journal.write({'currency_id': self.env.ref('base.USD').id})

        # Use an import wizard to process the file
        camt_file_path = get_module_resource(
            'account_bank_statement_import_camt',
            'test_camt_file',
            'camt_053_several_ibans.xml',)
        with open(camt_file_path, 'rb') as fd:
            camt_file = base64.b64encode(fd.read())

        wizard = self.env['account.bank.statement.import'].with_context(journal_id=bank_journal.id).create({'attachment_ids': [(0, 0, {
            'name': 'test file',
            'datas': camt_file,
        })]})

        with self.assertLogs(level="WARNING") as log_catcher:
            wizard.import_file()

        self.assertEqual(len(log_catcher.output), 1, "Exactly one warning should be logged")
        self.assertIn("The following statements will not be imported", log_catcher.output[0],
            "The logged warning warns about non-imported statements")

        # Check the imported bank statement
        bank_st_record = self.env['account.bank.statement'].search(
            [('name', '=', '2514988305.2019-05-23')]
        ).ensure_one()
        self.assertEqual(
            bank_st_record.balance_start, 1000.00, "Start balance not matched"
        )
        self.assertEqual(
            bank_st_record.balance_end_real, 1600.00, "End balance not matched"
        )

        # Check the imported bank statement line
        line = bank_st_record.line_ids.ensure_one()
        self.assertEqual(line.amount, 600.00, "Transaction not matched")


    def test_several_ibans_dont_match_camt_file_import(self):
        # Create a bank account and journal corresponding to the CAMT
        # file (same currency and account number)
        bank_journal = self.env['account.journal'].create(
            {
                'name': "Bank BE43 9787 8497 9701",
                'code': 'BNK69',
                'type': 'bank',
                'bank_acc_number': 'BE43 9787 8497 9701',
                'currency_id': self.env.ref('base.USD').id,
            }
        )

        # Use an import wizard to process the file
        camt_file_path = get_module_resource(
            'account_bank_statement_import_camt',
            'test_camt_file',
            'camt_053_several_ibans.xml',)
        with open(camt_file_path, 'rb') as fd:
            camt_file = base64.b64encode(fd.read())

        wizard = self.env['account.bank.statement.import'].with_context(journal_id=bank_journal.id).create({'attachment_ids': [(0, 0, {
            'name': 'test file',
            'datas': camt_file,
        })]})

        with self.assertLogs(camt_wizard_logger, level="WARNING") as log_catcher:
            with self.assertRaises(UserError) as error_catcher:
                wizard.import_file()

        self.assertEqual(len(log_catcher.output), 1, "Exactly one warning should be logged")
        self.assertIn("The following statements will not be imported", log_catcher.output[0],
            "The logged warning warns about non-imported statements")

        self.assertIn("Please check the currency on your bank journal.\n"
                      "No statements in currency {} were found in this CAMT file."\
                        .format((bank_journal.currency_id or bank_journal.company_id.currency_id).name),
            error_catcher.exception.args[0])


    def test_several_ibans_missing_journal_id_camt_file_import(self):
        # Create a bank account and journal corresponding to the CAMT
        # file (same currency and account number)
        bank_journal = self.env['account.journal'].create(
            {
                'name': "Bank BE43 9787 8497 9701",
                'code': 'BNK69',
                'type': 'bank',
                'currency_id': self.env.ref('base.USD').id,
                # missing bank account number
            }
        )

        # Use an import wizard to process the file
        camt_file_path = get_module_resource(
            'account_bank_statement_import_camt',
            'test_camt_file',
            'camt_053_several_ibans.xml',)
        with open(camt_file_path, 'rb') as fd:
            camt_file = base64.b64encode(fd.read())

        wizard = self.env['account.bank.statement.import'].with_context(journal_id=bank_journal.id).create({'attachment_ids': [(0, 0, {
            'name': 'test file',
            'datas': camt_file,
        })]})

        with self.assertLogs(camt_wizard_logger, level="WARNING") as log_catcher:
            with self.assertRaises(UserError) as error_catcher:
                wizard.import_file()

        self.assertEqual(len(log_catcher.output), 1, "Exactly one warning should be logged")
        self.assertIn("The following statements will not be imported", log_catcher.output[0],
            "The logged warning warns about non-imported statements")

        self.assertEqual(error_catcher.exception.args[0],
            ("Please set the IBAN account on your bank journal.\n\n"
             "This CAMT file is targeting several IBAN accounts but none match the current journal."))

    def test_date_and_time_format_camt_file_import(self):
        """
        This test aims to import a statement having dates specified in datetime format.
        """
        usd_currency = self.env.ref('base.USD')
        self.env.user.write({'company_id': self.usd_company.id})
        self._test_minimal_camt_file_import('camt_053_minimal_datetime.xml', usd_currency)

    def test_intraday_camt_file_import(self):
        """
        This test aims to import a statement having only an ITBD balance, where we have
        only one date, corresponding to the same opening and closing amount.
        """
        usd_currency = self.env.ref('base.USD')
        self.env.user.write({'company_id': self.usd_company.id})
        self._test_minimal_camt_file_import('camt_053_minimal_intraday.xml', usd_currency)

    def test_charges_camt_file_import(self):
        """
        This test aims to import a statement having transactions including charges in their
        total amount. In that case, we need to check that the retrieved amount is correct.
        """
        usd_currency = self.env.ref('base.USD')
        self.env.user.write({'company_id': self.usd_company.id})
        self._test_minimal_camt_file_import('camt_053_minimal_charges.xml', usd_currency)

    def test_charges_camt_file_import_02(self):
        """
        This test aims to import a statement having transactions including charges in their
        total amount. In that case, we need to check that the retrieved amount is correct.
        """
        usd_currency = self.env.ref('base.USD')
        self.env.user.write({'company_id': self.usd_company.id})
        self._test_minimal_camt_file_import('camt_053_minimal_charges_02.xml', usd_currency)
