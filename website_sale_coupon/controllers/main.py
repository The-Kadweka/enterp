# -*- coding: utf-8 -*-
from odoo import http
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.http import request
from datetime import datetime, timedelta


class WebsiteSale(WebsiteSale):

    @http.route(['/shop/pricelist'])
    def pricelist(self, promo, **post):
        order = request.website.sale_get_order()
        coupon_status = request.env['sale.coupon.apply.code'].sudo().apply_coupon(order, promo)
        if coupon_status.get('not_found'):
            return super(WebsiteSale, self).pricelist(promo, **post)
        elif coupon_status.get('error'):
            request.session['error_promo_code'] = coupon_status['error']
        return request.redirect(post.get('r', '/shop/cart'))

    @http.route(['/shop/payment'], type='http', auth="public", website=True)
    def payment(self, **post):
        self._recompute_coupon_lines()
        return super(WebsiteSale, self).payment(**post)

    @http.route(['/shop/cart'], type='http', auth="public", website=True)
    def cart(self, **post):
        limit = int(request.env['ir.config_parameter'].sudo().get_param('website_sale_coupon.seconds_between_update'))
        last_coupon_update = request.session.get('last_coupon_update')
        if not limit or not last_coupon_update or datetime.utcnow() - last_coupon_update >= timedelta(seconds=limit):
            order = request.website.sale_get_order()
            # use recompute_discounts if there is taxes (eg. so tax can be added back in sale_coupon_taxcloud)
            if order.mapped('order_line.tax_id'):
                order.recompute_discounts()
            else:
                order.recompute_coupon_lines()
            request.session['last_coupon_update'] = datetime.utcnow()
        return super(WebsiteSale, self).cart(**post)

    def _recompute_coupon_lines(self):
        order = request.website.sale_get_order()
        order.recompute_coupon_lines()
        request.session['last_coupon_update'] = datetime.utcnow()

    def _update_website_sale_coupon(self, **post):
        order = request.website.sale_get_order()
        order.recompute_discounts()
        free_shipping_lines = order._get_free_shipping_lines()
        currency = order.currency_id
        result = {}
        if free_shipping_lines:
            amount_free_shipping = sum(free_shipping_lines.mapped('price_subtotal'))
            result.update({
                'new_amount_delivery': self._format_amount(0.0, currency),
                'new_amount_untaxed': self._format_amount(order.amount_untaxed, currency),
                'new_amount_tax': self._format_amount(order.amount_tax, currency),
                'new_amount_total': self._format_amount(order.amount_total, currency),
                'new_amount_order_discounted': self._format_amount(order.reward_amount - amount_free_shipping, currency)
            })
        return result

    # Override
    # Add in the rendering the free_shipping_line
    def _get_shop_payment_values(self, order, **kwargs):
        values = super(WebsiteSale, self)._get_shop_payment_values(order, **kwargs)
        values['free_shipping_lines'] = order._get_free_shipping_lines()
        return values
