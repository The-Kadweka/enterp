# -*- coding: utf-8 -*-

from odoo import api, models, _, SUPERUSER_ID
from odoo.exceptions import ValidationError
from odoo.tools import float_compare, float_round, ormcache

from .taxcloud_request import TaxCloudRequest

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.multi
    def action_confirm(self):
        for order in self.filtered('fiscal_position_id.is_taxcloud'):
            order.validate_taxes_on_sales_order()
        return super(SaleOrder, self).action_confirm()

    @api.model
    def _get_TaxCloudRequest(self, api_id, api_key):
        return TaxCloudRequest(api_id, api_key)

    @api.model
    @ormcache('request_hash')
    def _get_all_taxes_values(self, request, request_hash):
        return request.get_all_taxes_values()

    @api.multi
    def validate_taxes_on_sales_order(self):
        company = self.company_id
        Param = self.env['ir.config_parameter']
        api_id = Param.sudo().get_param('account_taxcloud.taxcloud_api_id_{}'.format(company.id)) or Param.sudo().get_param('account_taxcloud.taxcloud_api_id')
        api_key = Param.sudo().get_param('account_taxcloud.taxcloud_api_key_{}'.format(company.id)) or Param.sudo().get_param('account_taxcloud.taxcloud_api_key')
        request = self._get_TaxCloudRequest(api_id, api_key)

        shipper = self.company_id or self.env.user.company_id
        request.set_location_origin_detail(shipper)
        request.set_location_destination_detail(self.partner_shipping_id)

        request.set_order_items_detail(self)

        response = self._get_all_taxes_values(request, request.hash)

        if response.get('error_message'):
            raise ValidationError(_('Unable to retrieve taxes from TaxCloud: ')+'\n'+response['error_message']+'\n\n'+_('The configuration of TaxCloud is in the Accounting app, Settings menu.'))

        tax_values = response['values']

        # warning: this is tightly coupled to TaxCloudRequest's _process_lines method
        # do not modify without syncing the other method
        for index, line in enumerate(self.order_line.filtered(lambda l: not l.display_type)):
            if line._get_taxcloud_price() >= 0.0 and line.product_uom_qty >= 0.0:
                price = line.price_unit * (1 - (line.discount or 0.0) / 100.0) * line.product_uom_qty
                if not price:
                    tax_rate = 0.0
                else:
                    tax_rate = tax_values[index] / price * 100
                if len(line.tax_id) != 1 or float_compare(line.tax_id.amount, tax_rate, precision_digits=3):
                    tax_rate = float_round(tax_rate, precision_digits=3)
                    tax = self.env['account.tax'].with_context(active_test=False).sudo().search([
                        ('amount', '=', tax_rate),
                        ('amount_type', '=', 'percent'),
                        ('type_tax_use', '=', 'sale'),
                        ('company_id', '=', company.id),
                    ], limit=1)
                    if tax and not tax.active:
                        tax.write({'active': True})
                    if not tax:
                        tax = self.env['account.tax'].sudo().create({
                            'name': 'Tax %.3f %%' % (tax_rate),
                            'amount': tax_rate,
                            'amount_type': 'percent',
                            'type_tax_use': 'sale',
                            'description': 'Sales Tax',
                            'company_id': company.id,
                        })
                    line.tax_id = tax
        return True

    def add_option_to_order_with_taxcloud(self):
        self.ensure_one()
        # portal user call this method with sudo
        if self.fiscal_position_id.is_taxcloud and self._uid == SUPERUSER_ID:
            self.validate_taxes_on_sales_order()


class SaleOrderLine(models.Model):
    """Defines getters to have a common facade for order and invoice lines in TaxCloud."""
    _inherit = 'sale.order.line'

    def _get_taxcloud_price(self):
        self.ensure_one()
        return self.price_unit

    def _get_qty(self):
        self.ensure_one()
        return self.product_uom_qty
