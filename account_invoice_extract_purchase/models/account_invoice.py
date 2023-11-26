# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.addons.account_invoice_extract.models.account_invoice import CLIENT_OCR_VERSION
from odoo.tests.common import Form

TOLERANCE = 0.02  # tolerance applied to the total when searching for a matching purchase order


class AccountInvoice(models.Model):
    _name = "account.invoice"
    _inherit = ['account.invoice']

    @api.model
    def _fill_invoice_with_ocr_values(self, record, ocr_results):
        if CLIENT_OCR_VERSION >= 120:
            supplier_ocr = ocr_results['supplier']['selected_value']['content'] if 'supplier' in ocr_results else ""
            vat_number_ocr = ocr_results['VAT_Number']['selected_value']['content'] if 'VAT_Number' in ocr_results else ""
            total_ocr = ocr_results['total']['selected_value']['content'] if 'total' in ocr_results else 0.0

            record._set_supplier(supplier_ocr, vat_number_ocr)

            if record.type == 'in_invoice' and record.partner_id and total_ocr:
                purchase_id_domain = self._onchange_allowed_purchase_ids()['domain']['purchase_id']
                purchase_id_domain += [('partner_id', '=', record.partner_id.id), ('amount_total', '>=', total_ocr - TOLERANCE), ('amount_total', '<=', total_ocr + TOLERANCE), ('state', '=', 'purchase')]
                matching_po = self.env['purchase.order'].search(purchase_id_domain)
                if len(matching_po) == 1:
                    with Form(record) as invoice_form:
                        invoice_form.purchase_id = matching_po
            super(AccountInvoice, self)._fill_invoice_with_ocr_values(record, ocr_results)
