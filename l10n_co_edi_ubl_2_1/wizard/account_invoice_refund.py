# coding: utf-8
from odoo import fields, models

from ..models.account_invoice import DESCRIPTION_CREDIT_CODE


class AccountInvoiceRefund(models.TransientModel):
    _inherit = 'account.invoice.refund'

    l10n_co_edi_description_code = fields.Selection(DESCRIPTION_CREDIT_CODE, string="Concepto", help="Colombian code for Credit Notes")

    def _get_refund(self, inv, mode):
        refund = super(AccountInvoiceRefund, self)._get_refund(inv, mode)
        refund.l10n_co_edi_description_code_credit = self.l10n_co_edi_description_code
        refund._onchange_type()
        return refund
