# -*- coding: utf-8 -*-

from .common import TestMXDeliveryGuideCommon

from odoo.tests import tagged

@tagged('external', 'external_l10n', 'post_install', 'post_install_l10n', '-at_install', '-standard')
class TestSendMXDeliveryGuide(TestMXDeliveryGuideCommon):
    def test_send_delivery_guide(self):
        self.picking.l10n_mx_edi_action_send_delivery_guide()
        self.assertFalse(self.picking.l10n_mx_edi_error)
        self.assertEqual(self.picking.l10n_mx_edi_status, 'sent')

@tagged('external', 'external_l10n', 'post_install', 'post_install_l10n', '-at_install', '-standard')
class TestMXDeliveryGuideXSD(TestMXDeliveryGuideCommon):
    def test_xsd_delivery_guide(self):
        cfdi = self.picking._l10n_mx_edi_create_delivery_guide()
        result = self.picking._l10n_mx_edi_validate_with_xsd(cfdi, raise_error=True)
        self.assertTrue(result)
