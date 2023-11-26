# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    intrastat_transport_mode_id = fields.Many2one('account.intrastat.code', string='Intrastat Transport Mode',
        readonly=True, states={'draft': [('readonly', False)]}, domain="[('type', '=', 'transport')]")
    intrastat_country_id = fields.Many2one('res.country', string='Intrastat Country',
        help='Intrastat country, arrival for sales, dispatch for purchases',
        compute='_compute_intrastat_country_id', readonly=False,
        states={'posted': [('readonly', True)], 'cancel': [('readonly', True)]}, store=True,
        domain=[('intrastat', '=', True)])

    @api.depends('partner_id')
    def _compute_intrastat_country_id(self):
        for move in self:
            if move.partner_id.country_id.intrastat:
                move.intrastat_country_id = move._get_invoice_intrastat_country_id()
            else:
                move.intrastat_country_id = False


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    intrastat_transaction_id = fields.Many2one('account.intrastat.code', string='Intrastat', domain="[('type', '=', 'transaction')]")
