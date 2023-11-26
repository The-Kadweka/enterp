# -*- coding: utf-8 -*-

import base64

from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo.tests.common import SavepointCase
from odoo.tools import misc

class TestMXDeliveryGuideCommon(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.cert = misc.file_open('l10n_mx_edi/demo/pac_credentials/certificate.cer', 'rb').read()
        cls.cert_key = misc.file_open('l10n_mx_edi/demo/pac_credentials/certificate.key', 'rb').read()
        cls.cert_password = '12345678a'
        cls.env.company.write({
            'name': 'company_1_data',
            'l10n_mx_edi_fiscal_regime': '601',
            'state_id': cls.env.ref('base.state_mx_son').id,
            'country_id': cls.env.ref('base.mx').id,
            'street': 'Campobasso Norte 3206/9000',
            'zip': '85134',
            'vat': 'EKU9003173C9',
        })

        certificate = cls.env['l10n_mx_edi.certificate'].create({
            'content': base64.encodebytes(cls.cert),
            'key': base64.encodebytes(cls.cert_key),
            'password': cls.cert_password,
        })
        cls.account_settings = cls.env['res.config.settings']
        cls.account_settings.create({
            'l10n_mx_edi_pac': 'finkok',
            'l10n_mx_edi_pac_test_env': True,
            'l10n_mx_edi_certificate_ids': [(6, 0, [certificate.id])],
        }).execute()

        cls.new_wh = cls.env['stock.warehouse'].create({
            'name': 'New Warehouse',
            'reception_steps': 'one_step',
            'delivery_steps': 'ship_only',
            'code': 'NWH'
        })

        cls.customer_location = cls.env.ref('stock.stock_location_customers')

        cls.productA = cls.env['product.product'].create({
            'name': 'Product A',
            'type': 'product',
            'l10n_mx_edi_code_sat_id': cls.env.ref('l10n_mx_edi.prod_code_sat_56101500').id,
            'weight': 1,
        })

        cls.partner_a = cls.env['res.partner'].create({
            'name': 'Partner A',
            'street': 'Street Calle',
            'city': 'Arteaga',
            'country_id': cls.env.ref('base.mx').id,
            'state_id': cls.env.ref('base.state_mx_coah').id,
            'zip': '25350',
            'vat': 'EME020824U4A',
        })

        cls.operator_pedro = cls.env['res.partner'].create({
            'name': 'Amigo Pedro',
            'vat': 'VAAM130719H60',
            'street': 'JESUS VALDES SANCHEZ',
            'city': 'Arteaga',
            'city_id': cls.env.ref('l10n_mx_edi.res_city_mx_coa_004').id,
            'country_id': cls.env.ref('base.mx').id,
            'state_id': cls.env.ref('base.state_mx_coah').id,
            'l10n_mx_edi_colony_code': '0347',
            'zip': '25350',
            'l10n_mx_edi_operator_licence': 'a234567890',
        })

        cls.figure_1 = cls.env['l10n_mx_edi.figure'].create({
            'type': '01',
            'operator_id': cls.operator_pedro.id,
        })

        cls.figure_2 = cls.env['l10n_mx_edi.figure'].create({
            'type': '02',
            'operator_id': cls.env.company.partner_id.id,
            'part_ids': [(4, cls.env.ref('l10n_mx_edi_stock.l10n_mx_edi_part_05').id)],
        })

        cls.vehicle_pedro = cls.env['l10n_mx_edi.vehicle'].create({
            'name': 'DEMOPERMIT',
            'transport_insurer': 'DEMO INSURER',
            'transport_insurance_policy': 'DEMO POLICY',
            'transport_perm_sct': 'TPAF10',
            'vehicle_model': '2020',
            'vehicle_config': 'T3S1',
            'vehicle_licence': 'ABC123',
            'trailer_ids': [(0, 0, {'name': 'trail1', 'sub_type': 'CTR003'})],
            'figure_ids': [(4, cls.figure_1.id, 0), (4, cls.figure_2.id, 0)],
        })

        cls.picking = cls.env['stock.picking'].create({
            'location_id': cls.new_wh.lot_stock_id.id,
            'location_dest_id': cls.customer_location.id,
            'picking_type_id': cls.new_wh.out_type_id.id,
            'partner_id': cls.partner_a.id,
            'l10n_mx_edi_transport_type': '01',
            'l10n_mx_edi_vehicle_id': cls.vehicle_pedro.id,
            'l10n_mx_edi_distance': 120,
        })

        cls.env['stock.move'].create({
            'name': cls.productA.name,
            'product_id': cls.productA.id,
            'product_uom_qty': 10,
            'product_uom': cls.productA.uom_id.id,
            'picking_id': cls.picking.id,
            'location_id': cls.new_wh.lot_stock_id.id,
            'location_dest_id': cls.customer_location.id,
            'state': 'confirmed',
            'description_picking': cls.productA.name,
        })

        cls.env['stock.quant']._update_available_quantity(cls.productA, cls.new_wh.lot_stock_id, 10.0)
        cls.picking.action_assign()
        cls.picking.move_lines[0].move_line_ids[0].qty_done = 10
        cls.picking.action_done()
