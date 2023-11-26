# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'


    dms_account_settings = fields.Boolean(related='company_id.dms_account_settings', readonly=False,
                                          string="Account Folder")
    account_folder = fields.Many2one('documents.folder', related='company_id.account_folder', readonly=False,
                                     string="account default folder")
    account_tags = fields.Many2many('documents.tag', 'account_tags_table',
                                    related='company_id.account_tags',
                                    readonly=False,
                                    string="Account Tags")
