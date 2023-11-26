# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dms_project_settings = fields.Boolean(related='company_id.dms_project_settings', readonly=False,
                                          string="Project Folder")
    project_folder = fields.Many2one('documents.folder', related='company_id.project_folder', readonly=False,
                                     string="project default folder")
    project_tags = fields.Many2many('documents.tag', 'project_tags_table',
                                    related='company_id.project_tags', readonly=False,
                                    string="Project Tags")
