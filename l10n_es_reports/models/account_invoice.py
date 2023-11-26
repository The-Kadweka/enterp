# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _
from odoo.exceptions import UserError
from odoo.tools.sql import column_exists, create_column


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    def _auto_init(self):
        if not column_exists(self.env.cr, "account_invoice", "l10n_es_reports_mod349_available"):
            create_column(self.env.cr, "account_invoice", "l10n_es_reports_mod349_available", "bool")
            mod349_countries = self.env.ref('base.europe').country_ids - self.env.ref('base.es')
            if mod349_countries:
                self.env.cr.execute(
                    """
                        UPDATE account_invoice
                        SET l10n_es_reports_mod349_available = true
                        FROM res_partner partner
                        WHERE partner.id = account_invoice.partner_id
                        AND partner.country_id IN %s
                    """, [tuple(mod349_countries.ids)]
                )
        return super()._auto_init()

    def _default_mod_349_invoice_type(self):
        invoice_type = self.env.context.get('type', False)

        if invoice_type == 'in_invoice':
            return 'A'
        if invoice_type == 'out_invoice':
            return 'E'

    def _mod_349_selection_values(self):
        context = self.env.context
        if context.get('type') in ('out_invoice', 'out_refund'):
            return[('E', _("E - Supply")), ('T', _("T - Triangular Operation")), ('S', _("S - Services sale")), ('M', _("M - Supply without taxes")), ('H', _("H - Supply without taxes delivered by a legal representative"))]
        if context.get('type') in ('in_invoice', 'in_refund'):
            return [('A', _("A - Acquisition")), ('T', _("T - Triangular Operation")), ('I', _("I - Services acquisition"))]
        # If no type is given in context, we give access to every possible value for the field
        return [('A', _("A - Acquisition")), ('E', _("E - Supply")), ('T', _("T - Triangular Operation")), ('S', _("S - Services sale")), ('I', _("I - Services acquisition")), ('M', _("M - Supply without taxes")), ('H', _("H - Supply without taxes delivered by a legal representative"))]

    l10n_es_reports_mod347_invoice_type = fields.Selection(string="Type for mod 347", selection=[('regular', "Regular operation"), ('insurance', "Insurance operation")], default='regular', help="Defines the category into which this invoice falls for mod 347 report.")
    l10n_es_reports_mod347_available = fields.Boolean(string="Available for Mod347", compute="_compute_l10n_es_reports_mod347_available", help="True if and only if the invoice MIGHT need to be reported on mod 347, i.e. it concerns an operation from a Spanish headquarter.")
    l10n_es_reports_mod349_invoice_type = fields.Selection(string="Type for mod 349", selection="_mod_349_selection_values", help="Defines the category into which this invoice falls for mod 349 report", default=_default_mod_349_invoice_type)
    l10n_es_reports_mod349_available = fields.Boolean(string="Available for Mod349", store=True, compute="_compute_l10n_es_reports_mod349_available", help="True if and only if the invoice must be reported on mod 349 report, i.e. it concerns an intracommunitary operation.")


    @api.depends('company_id')
    def _compute_l10n_es_reports_mod347_available(self):
        for record in self:
            # Even though Mod 347 is normally not required for EU operations, it is sometimes required, so the users
            # should be able to select it
            record.l10n_es_reports_mod347_available = record.company_id.country_id.code == "ES"

    @api.depends('partner_id.country_id')
    def _compute_l10n_es_reports_mod349_available(self):
        # Mod 349 is required for all european countries, except Spain
        mod349_countries = self.env.ref('base.europe').country_ids - self.env.ref('base.es')
        for record in self:
            record.l10n_es_reports_mod349_available = record.partner_id.country_id in mod349_countries

    @api.onchange('partner_id')
    def _onchange_partner_id_set_347_invoice_type(self):
        eu_countries = self.env.ref('base.europe').country_ids - self.env.ref('base.es')
        for record in self:
            # Mod 347 is normally not required for imports / exports within the EU, since those are already on the 349
            record.l10n_es_reports_mod347_invoice_type = False if record.partner_id.country_id in eu_countries else 'regular'

    def _get_refund_copy_fields(self):
        rslt = super(AccountInvoice, self)._get_refund_copy_fields()
        return rslt + ['l10n_es_reports_mod347_invoice_type', 'l10n_es_reports_mod349_invoice_type']

    @api.model
    def create(self,vals):
        res = super(AccountInvoice, self).create(vals)
        if not res.l10n_es_reports_mod349_invoice_type:
            res.l10n_es_reports_mod349_invoice_type = res.with_context(type=res.type)._default_mod_349_invoice_type()
        return res

    def invoice_validate(self):
        """ Overridden to require Spanish invoice type to be set if the company
        of the invoice uses a Spanish COA (so other companies using other COA
        on the same DB won't be force to use them).
        """
        rslt = super(AccountInvoice, self).invoice_validate()
        spanish_coa_list = [self.env.ref('l10n_es.account_chart_template_pymes'), self.env.ref('l10n_es.account_chart_template_assoc'), self.env.ref('l10n_es.account_chart_template_full')]
        for record in self:
            if record.company_id.chart_template_id in spanish_coa_list and \
            record.partner_id.country_id == self.env.ref('base.es', False) and \
            (not record.l10n_es_reports_mod347_invoice_type or (record.l10n_es_reports_mod349_available and not record.l10n_es_reports_mod349_invoice_type)):
                raise UserError(_("Please select a Spanish invoice type for this invoice."))
        return rslt