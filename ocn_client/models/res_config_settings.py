# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import uuid
import logging

import odoo
from odoo import fields, models, api
from odoo.addons.iap import jsonrpc

_logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = 'https://ocn.odoo.com'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ocn_push_notification = fields.Boolean('Push Notifications', config_parameter='ocn.ocn_push_notification')

    def _get_endpoint(self):
        return self.env['ir.config_parameter'].sudo().get_param('odoo_ocn.endpoint', DEFAULT_ENDPOINT)

    @api.model
    def create(self, vals):
        ir_params = self.env['ir.config_parameter'].sudo()
        if vals.get('ocn_push_notification') and not ir_params.get_param('odoo_ocn.project_id'):
            # Every time when user change setting, we need to validate ocn service
            params = {
                'ocnuuid': self._get_ocn_uuid(),
                'server_version': odoo.release.version,
                'db': self.env.cr.dbname,
                'company_name': self.env.user.company_id.name,
                'url': ir_params.get_param('web.base.url')
            }
            # Register instance to ocn service. Unique with ocn.uuid
            try:
                project_id = jsonrpc(self._get_endpoint() + '/iap/ocn/enable_service', params=params)
                ir_params.set_param('odoo_ocn.project_id', project_id)
            except Exception as e:
                _logger.error('An error occured while contacting the ocn server: %s', e.name)

            # Storing project id for generate token
        return super(ResConfigSettings, self).create(vals)

    @api.model
    def _get_ocn_uuid(self):
        push_uuid = self.env['ir.config_parameter'].sudo().get_param('ocn.uuid')
        if not push_uuid:
            push_uuid = str(uuid.uuid4())
            self.env['ir.config_parameter'].sudo().set_param('ocn.uuid', push_uuid)
        return push_uuid

    @api.model
    def register_device(self, device_key, device_name):
        if self.env['ir.config_parameter'].sudo().get_param('ocn.ocn_push_notification', False):
            values = {
                'ocn_uuid': self._get_ocn_uuid(),
                'user_name': self.env.user.name or self.env.user.login,
                'user_login': self.env.user.login,
                'device_name': device_name,
                'device_key': device_key
            }
            result = False
            try:
                result = jsonrpc(self._get_endpoint() + '/iap/ocn/register_device', params=values)
            except Exception as e:
                _logger.error('An error occured while contacting the ocn server: %s', e.name)

            if result:
                self.env.user.partner_id.ocn_token = result
                return result
        return False
