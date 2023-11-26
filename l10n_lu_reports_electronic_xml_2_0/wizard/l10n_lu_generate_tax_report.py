# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare
from ..models.l10n_lu_tax_report_data import YEARLY_SIMPLIFIED_NEW_TOTALS, YEARLY_SIMPLIFIED_FIELDS
from ..models.l10n_lu_tax_report_data import YEARLY_NEW_TOTALS, YEARLY_MONTHLY_FIELDS_TO_DELETE
from ..models.l10n_lu_tax_report_data import VAT_MANDATORY_FIELDS

class L10nLuGenerateTaxReport(models.TransientModel):
    """This wizard generates an xml tax report for Luxemburg according to the xml 2.0 standard."""
    _inherit = 'l10n_lu.generate.xml'
    _name = 'l10n_lu.generate.tax.report'
    _description = 'Generate Tax Report'

    simplified_declaration = fields.Boolean(default=True)
    period = fields.Selection(
        [('A', 'Annual'), ('M', 'Monthly'), ('T', 'Quarterly')],
        help="Technical field used to show the correct button in the view"
    )
    l10n_lu_annex_warning_visible = fields.Boolean(
        store=False,
        compute="_compute_l10n_lu_tax_report_annex_available",
        help="Technical field; flag to show/hide the warning that the annex is not included in the report."
    )

    @api.depends("period", "simplified_declaration")
    def _compute_l10n_lu_tax_report_annex_available(self):
        # Annex to the tax report not supported
        # Set this flag to True once the integration of the annex in the tax report is integrated
        annex_supported = False
        for r in self:
            r.l10n_lu_annex_warning_visible = not(annex_supported) and r.period == 'A' and not(r.simplified_declaration)

    @api.model
    def default_get(self, default_fields):
        rec = super().default_get(default_fields)
        options = self.env.context['tax_report_options']
        date_from = fields.Date.from_string(options['date'].get('date_from'))
        date_to = fields.Date.from_string(options['date'].get('date_to'))
        date_from_quarter = tools.date_utils.get_quarter_number(date_from)
        date_to_quarter = tools.date_utils.get_quarter_number(date_to)
        if date_from.month == date_to.month:
            rec['period'] = 'M'
        elif date_from_quarter == date_to_quarter:
            rec['period'] = 'T'
        else:
            rec['period'] = 'A'
        return rec

    def open_repartition_model(self):
        """
        Opens the l10n_lu.yearly.tax.report.manual for the current company and year.
        This is needed because Odoo's taxes and tags for LU are built from the monthly tax report,
        the yearly tax report is however more precise and requires further repartitions,
        which are to be filled in manually using l10n_lu.yearly.tax.report.manual.
        """
        def get_amount(decl, field):
            val = str(decl['field_values'].get(field, {}).get('value', '0.00'))
            return float(val.replace(',', '.'))

        options = self.env.context['tax_report_options']
        decl = self.env['account.generic.tax.report']._get_lu_electronic_report_values(options)['forms'][0]

        yearly_tax_report_manual = self.env['l10n_lu.yearly.tax.report.manual'].search(
            [('company_id', '=', self.env.company.id), ('year', '=', str(decl['year']))],
            limit=1)
        if not yearly_tax_report_manual:
            yearly_tax_report_manual = self.env['l10n_lu.yearly.tax.report.manual'].create({
                'year': str(decl['year']),
                'company_id': self.env.company.id,
            })

        yearly_tax_report_manual.report_section_472 = get_amount(decl, '472')
        yearly_tax_report_manual.report_section_455 = get_amount(decl, '455')
        yearly_tax_report_manual.report_section_456 = get_amount(decl, '456')
        yearly_tax_report_manual.report_section_457 = get_amount(decl, '457')
        yearly_tax_report_manual.report_section_458 = get_amount(decl, '458')
        yearly_tax_report_manual.report_section_459 = get_amount(decl, '459')
        yearly_tax_report_manual.report_section_460 = get_amount(decl, '460')
        yearly_tax_report_manual.report_section_461 = get_amount(decl, '461')

        context = self.env.context.copy()
        context['calling_wizard_id'] = self.id
        view_id = self.env.ref('l10n_lu_reports_electronic_xml_2_0.view_l10n_lu_yearly_tax_report_manual_export').id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tax Report Data'),
            'view_mode': 'form',
            'res_model': 'l10n_lu.yearly.tax.report.manual',
            'target': 'new',
            'res_id': yearly_tax_report_manual.id,
            'views': [[view_id, 'form']],
            'context': context,
        }

    def _lu_get_declarations(self, declaration_template_values):
        """
        Gets the formatted values for LU's tax report.
        Exact format depends on the period (monthly, quarterly, annual(simplified)).
        """
        options = self.env.context['tax_report_options']
        form = self.env['account.generic.tax.report']._get_lu_electronic_report_values(options)['forms'][0]
        self.period = form['declaration_type'][-1]
        form['field_values'] = self._remove_zero_fields(form['field_values'])
        if self.period == 'A':
            options = self.env.context['tax_report_options']
            date_from = fields.Date.from_string(options['date'].get('date_from'))
            date_to = fields.Date.from_string(options['date'].get('date_to'))
            self._adapt_to_annual_report(form, date_from, date_to)
            if self.simplified_declaration:  # adapt to simplified annual declaration
                self._adapt_to_simplified_annual_declaration(form)
            else:  # adapt to annual declaration
                self._adapt_to_full_annual_declaration(form)

        form['model'] = 1
        declaration = {'declaration_singles': {'forms': [form]}, 'declaration_groups': []}
        declaration.update(declaration_template_values)
        return {'declarations': [declaration]}

    def _add_yearly_fields(self, data, form):
        numeric_fields = {
            '001': data.report_section_001, '002': data.report_section_002, '003': data.report_section_003,
            '004': data.report_section_004, '005': data.report_section_005, '007': data.report_section_007,
            '008': data.report_section_008, '009': data.report_section_009, '010': data.report_section_010,
            # field 010 reports to the annex
            '389': data.report_section_010, '388': data.report_section_010, '011': data.report_section_011,
            '013': data.report_section_013, '202': data.report_section_202, '077': data.report_section_077,
            '078': data.report_section_078, '079': data.report_section_079, '404': data.report_section_404,
            '081': data.report_section_081, '082': data.report_section_082, '083': data.report_section_083,
            '405': data.report_section_405, '085': data.report_section_085, '086': data.report_section_086,
            '087': data.report_section_087, '406': data.report_section_406
        }
        for k, v in numeric_fields.items():
            if v != 0.00 or k == '013':  # field 013 is mandatory
                form['field_values'][k] = {'value': v, 'field_type': 'float'}
        
        return form
        
    def _adapt_to_full_annual_declaration(self, form, report_id=None):
        """
        Adapts the report to the annual format, comprising additional fields and apppendices.
        (https://ecdf-developer.b2g.etat.lu/ecdf/forms/popup/TVA_DECA_TYPE/2020/en/1/preview)
        """
        if report_id:
            # if the function is called from the manual report itself, we don't have tax_report_data_id in the context and have to pass the id
            data = self.env['l10n_lu.yearly.tax.report.manual'].browse(report_id)
        else:
            data = self.env['l10n_lu.yearly.tax.report.manual'].browse(self.env.context['tax_report_data_id'])
        # Check the correct allocation of monthly fields
        allocation_dict = {
            '472': data.report_section_472_rest,
            '455': data.report_section_455_rest,
            '456': data.report_section_456_rest,
            '457': data.report_section_457_rest,
            '458': data.report_section_458_rest,
            '459': data.report_section_459_rest,
            '460': data.report_section_460_rest,
            '461': data.report_section_461_rest
        }
        rest = [k for k, v in allocation_dict.items() if float_compare(v, 0.0, 2) != 0]
        if rest:
            raise ValidationError(_("The following monthly fields haven't been completely allocated yet: ") + str(rest))

        if data.phone_number:
            form['field_values']['237'] = {'value': data.phone_number, 'field_type': 'char'}
        if data.books_records_documents:
            form['field_values']['238'] = {'value': data.books_records_documents, 'field_type': 'char'}
        if data.avg_nb_employees_with_salary:
            form['field_values']['108'] = {'value': data.avg_nb_employees_with_salary, 'field_type': 'float'}
        if data.avg_nb_employees_with_no_salary:
            form['field_values']['109'] = {'value': data.avg_nb_employees_with_no_salary, 'field_type': 'float'}
        if data.avg_nb_employees:
            form['field_values']['110'] = {'value': data.avg_nb_employees, 'field_type': 'float'}

        form = self._add_yearly_fields(data, form)
        # Character fields
        if data.report_section_007:
            # Only fill in field 206 (additional Total Sales/Receipts line), which specifies what field
            # 007 refers to, if 007 has something to report
            form['field_values']['206'] = {'value': data.report_section_206, 'field_type': 'char'}
        # Field 010 (use of goods considered business assets for purposes other than those of the business) is specified
        # in the annex part B: we put everything in "Other assets" (field 388) and specify that in the detail line (field 387)
        if data.report_section_010:
            form['field_values']['387'] = {'value': 'Report from 010', 'field_type': 'char'}
        # Appendix part F: Names and addresses to be specified (accountant/lessor)
        for k, v in {'397': data.report_section_397, '398': data.report_section_398, '399': data.report_section_399,
                     '400': data.report_section_400, '401': data.report_section_401, '402': data.report_section_402}.items():
            if v:
                form['field_values'][k] = {'value': v, 'field_type': 'char'}

        # Remove monthly fields
        for f in YEARLY_MONTHLY_FIELDS_TO_DELETE:
            form['field_values'].pop(f, None)
        # Add new totals
        for total, f in YEARLY_NEW_TOTALS.items():
            form['field_values'][total] = {'value': (
                sum([form['field_values'].get(a) and float(str(form['field_values'][a]['value']).replace(',', '.')) or 0.00 for a in f.get('add', [])]) -
                sum([form['field_values'].get(a) and float(str(form['field_values'][a]['value']).replace(',', '.')) or 0.00 for a in f.get('subtract', [])])),
                                           'field_type': 'float'}
        form['field_values']['998'] = {'value': '1' if data.submitted_rcs else '0', 'field_type': 'boolean'}
        form['field_values']['999'] = {'value': '0' if data.submitted_rcs else '1', 'field_type': 'boolean'}

    def _adapt_to_simplified_annual_declaration(self, form):
        """
        Adapts the tax report (built for the monthly tax report) to the format required
        for the simplified annual tax declaration.
        (https://ecdf-developer.b2g.etat.lu/ecdf/forms/popup/TVA_DECAS_TYPE/2020/en/1/preview)
        """
        form['declaration_type'] = 'TVA_DECAS'
        for total, addends in YEARLY_SIMPLIFIED_NEW_TOTALS.items():
            form['field_values'][total] = {
                'value': sum([form['field_values'].get(a) and float(str(form['field_values'][a]['value']).replace(',', '.')) or 0.00 for a in addends]),
                'field_type': 'float'}
        # "Supply of goods by a taxable person applying the common flat-rate scheme for farmers" fields are not supported;
        form['field_values']['801'] = {'value': 0.00, 'field_type': 'float'}
        form['field_values']['802'] = {'value': 0.00, 'field_type': 'float'}
        # Only keep valid declaration fields
        form['field_values'] = {k: v for k, v in form['field_values'].items() if k in YEARLY_SIMPLIFIED_FIELDS}

    @api.model
    def _adapt_to_annual_report(self, form, date_from, date_to):
        """Adds date fields specific to annual tax reports in LU."""
        form['field_values'].update({
            '233': {'value': str(date_from.day), 'field_type': 'number'},
            '234': {'value': str(date_from.month), 'field_type': 'number'},
            '235': {'value': str(date_to.day), 'field_type': 'number'},
            '236': {'value': str(date_to.month), 'field_type': 'number'}
        })

    def _remove_zero_fields(self, field_values):
        """Removes declaration fields at 0, unless they are mandatory fields or parents of filled-in fields."""
        parents = self.env['account.tax.report.line'].search([]).mapped(lambda r: (r.code, r.parent_id.code))
        parents_dict = {p[0]: p[1] for p in parents}
        new_field_values = {}
        for f in field_values:
            if f in VAT_MANDATORY_FIELDS or field_values[f]['field_type'] not in ('float', 'number')\
                    or (field_values[f]['field_type'] == 'number' and field_values[f]['value'] != '0,00')\
                    or (field_values[f]['field_type'] == 'float' and float_compare(field_values[f]['value'], 0.0, 2) != 0):
                new_field_values[f] = field_values[f]
                # If a field is filled in, the parent should be filled in too, even if at 0.00;
                parent = parents_dict.get('LUTAX_' + f)
                if parent and not new_field_values.get(parent[6:]):
                    new_field_values[parent[6:]] = {'value': '0,00', 'field_type': 'number'}
        return new_field_values
