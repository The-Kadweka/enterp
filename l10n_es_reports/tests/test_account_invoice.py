from odoo.addons.account.tests.account_test_classes import AccountingTestCase
from odoo.tests import tagged, Form


@tagged('post_install', '-at_install')
class TestAccountInvoice(AccountingTestCase):
    def setUp(self):
        super().setUp()
        self.account_receivable = self.env['account.account'].search(
            [('user_type_id', '=', self.env.ref('account.data_account_type_receivable').id)], limit=1)
        self.account_revenue = self.env['account.account'].search(
            [('user_type_id', '=', self.env.ref('account.data_account_type_revenue').id)], limit=1)
        self.company = self.env.user.company_id
        self.partner_es = self.env['res.partner'].create({
            'name': 'España',
            'country_id': self.env.ref('base.es').id,
            'property_account_receivable_id': self.account_receivable.id,
            'property_account_payable_id': self.account_receivable.id,
            'company_id': self.company.id,
            'customer': True
        })
        self.partner_eu = self.env['res.partner'].create({
            'name': 'France',
            'country_id': self.env.ref('base.fr').id,
            'property_account_receivable_id': self.account_receivable.id,
            'property_account_payable_id': self.account_receivable.id,
            'company_id': self.company.id,
            'customer': True
        })

    def create_invoice(self, partner_id):
        f = Form(self.env['account.invoice'])
        f.partner_id = partner_id
        f.type = 'out_invoice'
        f.account_id = self.account_receivable
        with f.invoice_line_ids.new() as line:
            line.product_id = self.env.ref("product.product_product_4")
            line.quantity = 1
            line.price_unit = 100
            line.name = 'something'
            line.account_id = self.account_revenue
        invoice = f.save()
        return invoice

    def test_mod347_default_include_domestic_invoice(self):
        invoice = self.create_invoice(self.partner_es)
        self.assertEqual(invoice.l10n_es_reports_mod347_invoice_type, 'regular')

    def test_mod347_exclude_intracomm_invoice(self):
        invoice = self.create_invoice(self.partner_eu)
        self.assertFalse(invoice.l10n_es_reports_mod347_invoice_type)
