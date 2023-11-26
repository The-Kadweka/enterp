# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    l10n_mx_edi_weight = fields.Float(compute='_cal_move_line_weight', digits='Stock Weight', compute_sudo=True)

    def _cal_move_line_weight(self):
        moves_lines_with_weight = self.filtered(lambda ml: ml.product_id.weight > 0.00)
        for line in moves_lines_with_weight:
            qty = line.product_qty or line.product_uom_id._compute_quantity(line.qty_done, line.product_id.uom_id, rounding_method='HALF-UP')
            line.l10n_mx_edi_weight = qty * line.product_id.weight
        (self - moves_lines_with_weight).l10n_mx_edi_weight = 0
