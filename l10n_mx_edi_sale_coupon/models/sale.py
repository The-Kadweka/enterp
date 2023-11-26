# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models

class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.multi
    def action_invoice_create(self, grouped=False, final=False):
        invoice_ids = super(SaleOrder, self).action_invoice_create(grouped, final)
        return invoice_ids + self._l10n_mx_edi_prepare_refund_sale_coupon(invoice_ids)

    def _l10n_mx_edi_prepare_refund_sale_coupon(self, invoice_ids):
        inv_obj = refunds = self.env['account.invoice']
        invoices_with_reward = inv_obj.browse(invoice_ids).filtered(lambda inv:
                    inv.type == 'out_invoice'and
                    inv.l10n_mx_edi_is_required() and
                    any(inv.mapped('invoice_line_ids.sale_line_ids.is_reward_line')))
        for invoice in invoices_with_reward:
            vals_refund = inv_obj._prepare_refund(invoice)
            vals_refund.pop('invoice_line_ids', None)
            vals_refund.pop('tax_line_ids', None)
            vals_refund['date_invoice'] = invoice.date_invoice
            vals_refund['origin'] = invoice.origin
            refund_invoice = inv_obj.create(vals_refund)
            for line in invoice.invoice_line_ids.filtered(lambda l: l.price_unit < 0):
                line.write({
                    'invoice_id': refund_invoice.id,
                    'price_unit': abs(line.price_unit),
                })
            invoice.compute_taxes()
            refund_invoice.compute_taxes()
            refunds |= refund_invoice
        return refunds.ids

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _compute_invoice_status(self):
        super(SaleOrderLine, self)._compute_invoice_status()
        for line in self:
            if line.is_reward_line and line.invoice_lines:
                line.invoice_status = 'invoiced'
