# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class ResConfigSettings(models.TransientModel):

    _inherit = 'res.config.settings'

    @api.multi
    def set_values(self):
        super(ResConfigSettings, self).set_values()
        sign_request_rule = self.env.ref('sign.ir_rule_sign_request_company', raise_if_not_found=False)
        if sign_request_rule:
            sign_request_rule.write({'active': not self.company_share_partner})
