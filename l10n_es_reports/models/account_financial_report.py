# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, fields, _

from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

from odoo.exceptions import UserError

from datetime import datetime


class AccountFinancialReportLine(models.Model):
    _inherit = 'account.financial.html.report.line'

    l10n_es_mod347_threshold = fields.Float("Mod.347 Partner Threshold", help="""
The threshold value, in EURO, to be applied on invoice journal items  grouped by partner in the Modelo 347 report.
Only the partners having a debit sum value strictly superior to the threshold over the fiscal year
will be taken into account in this report.
This feature is only supported/useful in spanish MOD347 report.""")

    def _parse_threshold_parameter(self, company, date):
        """ Parses the content of the l10n_es_mod347_threshold field, returning its
        value in company currency.
        """
        self.ensure_one()
        if self.l10n_es_mod347_threshold:
            amount = self.l10n_es_mod347_threshold
            threshold_currency = self.env['res.currency'].search([('name', '=', 'EUR')])

            if not threshold_currency:
                raise UserError(_("Currency %s, used for a threshold in this report, is either nonexistent or inactive. Please create or activate it." % threshold_currency.name))

            company_currency = self.env.company.currency_id
            return threshold_currency._convert(amount, company_currency, company, date)

    def _get_with_statement(self):
        self.ensure_one()
        financial_report = self._get_financial_report()
        if financial_report and financial_report.l10n_es_reports_modelo_number == '347' and self.l10n_es_mod347_threshold:
            if self.groupby != 'partner_id':
                raise UserError(_("Trying to use a groupby threshold for a line without grouping by partner_id isn't supported."))

            company = self.env['res.company'].browse(self.env.context['company_ids'][0])
            from_fiscalyear_dates = company.compute_fiscalyear_dates(datetime.strptime(self.env.context['date_from'], DEFAULT_SERVER_DATE_FORMAT))
            to_fiscalyear_dates = company.compute_fiscalyear_dates(datetime.strptime(self.env.context['date_to'], DEFAULT_SERVER_DATE_FORMAT))

            # ignore the threshold if from and to dates belong to different fiscal years
            if from_fiscalyear_dates == to_fiscalyear_dates:
                threshold_value = self._parse_threshold_parameter(company, from_fiscalyear_dates['date_to'])
                tables, where_clause, where_params = self.env['account.move.line']._query_get(domain=self._get_aml_domain())

                sql_with = f"""WITH account_move_line
                              AS (SELECT *
                                  FROM account_move_line
                                  WHERE partner_id IN (
                                      SELECT account_move_line.partner_id
                                      FROM {tables}
                                      WHERE {where_clause}
                                      GROUP BY account_move_line.partner_id
                                      HAVING ABS(SUM(debit - credit)) > %s
                                  )
                              )
                           """

                with_params = where_params + [threshold_value]

                return sql_with, with_params

        return '', []

    def _build_query_rows_count(self, groupby, tables, where_clause, params):
        query, params = super()._build_query_rows_count(groupby, tables, where_clause, params)
        with_query, with_params = self._get_with_statement()
        return with_query + query, with_params + params

    def _build_query_compute_line(self, select, tables, where_clause, params):
        query, params = super()._build_query_compute_line(select, tables, where_clause, params)
        with_query, with_params = self._get_with_statement()
        return with_query + query, with_params + params

    def _build_query_eval_formula(self, groupby, select, tables, where_clause, params):
        query, params = super()._build_query_eval_formula(groupby, select, tables, where_clause, params)
        with_query, with_params = self._get_with_statement()
        return with_query + query, with_params + params
