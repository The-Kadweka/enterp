# coding: utf-8
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "EDI Cancellation for Mexican Localization",
    'author': "Vauxoo",
    'website': "http://www.vauxoo.com",
    'license': 'OEEL-1',
    'category': 'Hidden',
    'version': '1.0',
    'depends': [
        'l10n_mx_edi',
    ],
    'data': [
        'data/ir_cron_data.xml',
        'data/server_action_data.xml',
        'views/account_invoice_view.xml',
    ],
    'demo': [
    ],
    'installable': True,
    'auto_install': False,
}
