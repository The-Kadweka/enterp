# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo.addons.delivery_easypost.models.easypost_request import EasypostRequest
from odoo.addons.delivery_easypost.tests.common import EasypostTestCommon
from odoo.tests import tagged


@tagged('-standard', 'external')
class TestEasypostRequest(EasypostTestCommon):
    def setUp(self):
        super().setUp()
        self.easypost = EasypostRequest("XXX", lambda x: None)

    def test_prepare_order_shipments(self):
        SaleOrder = self.env["sale.order"]
        sol_1_vals = {"product_id": self.server.id}
        sol_2_vals = {"product_id": self.miniServer.id}
        so_vals_fedex = {"partner_id": self.jackson.id, "order_line": [(0, None, sol_1_vals), (0, None, sol_2_vals)]}

        sale_order_fedex = SaleOrder.create(so_vals_fedex)
        shipment = self.easypost._prepare_order_shipments(self.easypost_fedex_carrier, sale_order_fedex)

        self.assertEquals(shipment["order[shipments][0][parcel][weight]"], 80)
        self.assertFalse("order[shipments][1][parcel][weight]" in shipment, "Should have only 1 shipment")

    def test_prepare_order_shipments_multiple(self):
        self.fedex_default_packaging.max_weight = 3
        SaleOrder = self.env["sale.order"]
        sol_1_vals = {"product_id": self.server.id}
        sol_2_vals = {"product_id": self.miniServer.id}
        so_vals_fedex = {"partner_id": self.jackson.id, "order_line": [(0, None, sol_1_vals), (0, None, sol_2_vals)]}

        sale_order_fedex = SaleOrder.create(so_vals_fedex)
        shipment = self.easypost._prepare_order_shipments(self.easypost_fedex_carrier, sale_order_fedex)

        self.assertEquals(shipment["order[shipments][0][parcel][weight]"], 3 * 16, "First package weight")
        self.assertTrue("order[shipments][1][parcel][weight]" in shipment, "Should have 2 shipments")
        self.assertEquals(shipment["order[shipments][1][parcel][weight]"], 2 * 16, "Leftover weight")
        self.assertFalse("order[shipments][2][parcel][weight]" in shipment, "Should have 2 shipments")

    def test_prepare_order_shipments_no_max_weight(self):
        self.fedex_default_packaging.max_weight = 0
        SaleOrder = self.env["sale.order"]
        sol_1_vals = {"product_id": self.server.id}
        sol_2_vals = {"product_id": self.miniServer.id}
        so_vals_fedex = {"partner_id": self.jackson.id, "order_line": [(0, None, sol_1_vals), (0, None, sol_2_vals)]}

        sale_order_fedex = SaleOrder.create(so_vals_fedex)
        shipment = self.easypost._prepare_order_shipments(self.easypost_fedex_carrier, sale_order_fedex)

        self.assertEquals(shipment["order[shipments][0][parcel][weight]"], 80)
        self.assertFalse('order[shipments][1][parcel][weight]' in shipment, 'Should have only 1 shipment')
