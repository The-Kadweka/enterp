# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import odoo.tests
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from odoo import fields
from odoo.tests.common import Form


class TestRentalCommon(odoo.tests.common.SingleTransactionCase):

    def setUp(self):
        super(TestRentalCommon, self).setUp()

        self.product_id = self.env.ref('sale_renting.rental_product_1')
        self.product_template_id = self.product_id.product_tmpl_id

        self.product_template_id.rental_pricing_ids.unlink()
        # blank the demo pricings

        PRICINGS = [
            {
                'duration': 1.0,
                'unit': 'hour',
                'price': 3.5,
            }, {
                'duration': 5.0,
                'unit': 'hour',
                'price': 15.0,
            }, {
                'duration': 15.0,
                'unit': 'hour',
                'price': 40.0,
            }, {
                'duration': 1.0,
                'unit': 'day',
                'price': 60.0,
            },
        ]

        for pricing in PRICINGS:
            pricing.update(product_template_id=self.product_template_id.id)
            pricing = self.env['rental.pricing'].create(pricing)

        partner = self.env['res.partner'].create({'name': 'A partner'})

        self.sale_order = self.env['sale.order'].create({
            'partner_id': partner.id,
        })

    def test_availability(self):
        # Pickup, return some, check different periods
        return

    def test_pricing(self):
        # check pricing returned = expected
        self.assertEquals(
            self.product_id._get_best_pricing_rule(duration=9.0, unit='hour')._compute_price(9.0, 'hour'),
            30.0
        )

        self.assertEquals(
            self.product_id._get_best_pricing_rule(duration=11.0, unit='hour')._compute_price(11.0, 'hour'),
            38.5
        )

        self.assertEquals(
            self.product_id._get_best_pricing_rule(duration=16.0, unit='hour')._compute_price(16.0, 'hour'),
            56.0
        )

        self.assertEquals(
            self.product_id._get_best_pricing_rule(duration=20, unit='hour')._compute_price(20.0, 'hour'),
            60.0
        )

        self.assertEquals(
            self.product_id._get_best_pricing_rule(duration=24.0, unit='hour')._compute_price(24.0, 'hour'),
            60.0
        )

    def test_pricing_advanced(self):
        # with pricings applied only to some variants ...
        return

    def test_delay_pricing(self):
        # Return Products late and verify duration is correct.
        self.product_id.extra_hourly = 2.5
        self.product_id.extra_daily = 15.0

        self.assertEquals(
            self.product_id._compute_delay_price(timedelta(hours=5.0)),
            12.5
        )

        self.assertEquals(
            self.product_id._compute_delay_price(timedelta(hours=5.0, days=6)),
            102.5
        )

    def test_pricelist_discount_excluded(self):
        # Add group 'Discount on Lines' to the user
        self.env.user.write({'groups_id': [(4, self.env.ref('product.group_discount_per_so_line').id)]})

        pricelist_id_discount_excluded = self.env['product.pricelist'].create({
            'name': 'Discount excluded',
            'discount_policy': 'without_discount',
        })

        self.env['product.pricelist.item'].create({
            'pricelist_id': pricelist_id_discount_excluded.id,
            'compute_price': 'percentage',
            'percent_price': 10.0,
        })

        self.sale_order.pricelist_id = pricelist_id_discount_excluded

        now = fields.date.today()
        one_day_later = now + relativedelta(days=1)

        sol = self.env['sale.order.line'].create({
            'product_id': self.product_id.id,
            'product_uom_qty': 1,
            'price_unit': self.product_id._get_best_pricing_rule(duration=1, unit='day')._compute_price(1, 'day'),
            'order_id': self.sale_order.id,
            'reservation_begin': now,
            'pickup_date': now,
            'return_date': one_day_later,
            'is_rental': True,
        })

        self.assertEqual(sol.discount, 0, 'Discount should not apply on Rental order line')
        self.assertEqual(sol.price_unit, 60.0, 'Price should be equal to pricing for 1 day')

        with Form(self.sale_order, view='sale_renting.rental_order_form_view') as so_form:
            sol_form = so_form.order_line.edit(0)
            sol_form.product_uom_qty = 2
            self.assertEqual(sol_form.product_uom_qty, 2, 'Check that quantity has been updated')
            self.assertEqual(sol_form.discount, 0, 'Discount should not be updated')
            self.assertEqual(sol_form.price_unit, 60.0, 'Unit price should still be equal to pricing for 1 day')

    def test_is_add_to_cart_possible(self):
        # Check that `is_add_to_cart_possible` returns True when
        # the product is active and can be rent or/and sold
        self.product_template_id.write({'sale_ok': False, 'rent_ok': False})
        self.assertFalse(self.product_template_id._is_add_to_cart_possible())
        self.product_template_id.write({'sale_ok': True})
        self.assertTrue(self.product_template_id._is_add_to_cart_possible())
        self.product_template_id.write({'sale_ok': False, 'rent_ok': True})
        self.assertTrue(self.product_template_id._is_add_to_cart_possible())
        self.product_template_id.write({'sale_ok': True})
        self.assertTrue(self.product_template_id._is_add_to_cart_possible())
        self.product_template_id.write({'active': False})
        self.assertFalse(self.product_template_id._is_add_to_cart_possible())

    # TODO availability testing with sale_rental functions? (no stock)

@odoo.tests.tagged('post_install', '-at_install')
class TestUi(odoo.tests.HttpCase):

    def test_rental_flow(self):
        # somehow, the name_create and onchange of the partner_id
        # in a quotation trigger a re-rendering that loses
        # the focus of some fields, preventing the tour to
        # run successfully if a partner is created during the flow
        # create it in advance here instead
        self.env['res.partner'].name_create('Agrolait')
        self.start_tour("/web", 'rental_tour', login="admin")
