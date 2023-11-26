from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """This code was added in the `l10n_mx_edi.product.sat.code.csv` file
    but that file is loaded only when the `l10n_mx_edi` module is installed (by hook).
    Because of that, if the module was already installed when the patch was applied,
    they weren't added, so they need to be added manually."""

    env = api.Environment(cr, SUPERUSER_ID, {})
    field_names = ['id', 'code', 'name', 'applies_to', 'active']
    new_covid_sat_codes = [
        ['prod_code_sat_85121811', '85121811',
         'Servicios de laboratorios de detección del COVID', 'product', '1'],
    ]
    ctx = {'current_module': 'l10n_mx_edi', 'noupdate': True}
    env['l10n_mx_edi.product.sat.code'].with_context(ctx).load(
        field_names, new_covid_sat_codes)
