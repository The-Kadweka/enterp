# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import _, api, models, fields
from odoo.exceptions import ValidationError
import re


class ResCompany(models.Model):
    _inherit = "res.company"

    matr_number = fields.Char(string="Matr Number")
    ecdf_prefix = fields.Char(string="eCDF Prefix")

    # Technical field for invisible condition on company view for LU-specific fields
    country_code = fields.Char(related='country_id.code', readonly=True)

    @api.constrains('matr_number')
    def _check_company_matr_number(self):
        matr_number_re = re.compile('[0-9]{11,13}')
        for record in self:
            if record.matr_number and not matr_number_re.match(record.matr_number):
                raise ValidationError(_("The company's Matr. Number is not valid. There should be between 11 and 13 digits."))

    @api.constrains('ecdf_prefix')
    def _check_company_ecdf_prefix(self):
        ecdf_re = re.compile('[0-9A-Z]{6}')
        for record in self:
            if record.ecdf_prefix and not ecdf_re.match(record.ecdf_prefix):
                raise ValidationError(_("The company's ECDF Prefix is not valid. There should be exactly 6 characters."))
