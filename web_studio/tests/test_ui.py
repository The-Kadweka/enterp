# Part of Odoo. See LICENSE file for full copyright and licensing details.
# -*- coding: utf-8 -*-

import unittest

import odoo.tests


@odoo.tests.tagged('post_install', '-at_install')
class TestUi(odoo.tests.HttpCase):

    @unittest.skip('broken, unmaintained for 12.0')
    def test_new_app_and_report(self):
        self.phantom_js("/web?studio=app_creator",
                        "odoo.__DEBUG__.services['web_tour.tour'].run('web_studio_new_app_tour')",
                        "odoo.__DEBUG__.services['web_tour.tour'].tours.web_studio_new_app_tour.ready",
                        login="admin")

        # the report tour is based on the result of the former tour
        self.phantom_js("/web",
                        "odoo.__DEBUG__.services['web_tour.tour'].run('web_studio_new_report_tour')",
                        "odoo.__DEBUG__.services['web_tour.tour'].tours.web_studio_new_report_tour.ready",
                        login="admin")
        self.phantom_js("/web",
                        "odoo.__DEBUG__.services['web_tour.tour'].run('web_studio_new_report_basic_layout_tour')",
                        "odoo.__DEBUG__.services['web_tour.tour'].tours.web_studio_new_report_basic_layout_tour.ready",
                        login="admin")
    @unittest.skip('broken, unmaintained for 12.0')
    def test_rename(self):
        self.phantom_js("/web?studio=app_creator",
                        "odoo.__DEBUG__.services['web_tour.tour'].run('web_studio_tests_tour')",
                        "odoo.__DEBUG__.services['web_tour.tour'].tours.web_studio_tests_tour.ready",
                        login="admin")
