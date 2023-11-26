# coding: utf-8
import io
import xml.dom.minidom
import zipfile
import pytz

from collections import defaultdict
from datetime import timedelta
from functools import lru_cache
from os import listdir

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_TIME_FORMAT
from odoo.tools.float_utils import float_compare

DESCRIPTION_CREDIT_CODE = [
    ("1", "Devolución parcial de los bienes y/o no aceptación parcial del servicio"),
    ("2", "Anulación de factura electrónica"),
    ("3", "Rebaja total aplicada"),
    ("4", "Ajuste de precio"),
    ("5", "Otros"),
    ("6", "Otros (Inactive)")
]

DESCRIPTION_DEBIT_CODE = [
    ("1", 'Intereses'),
    ("2", 'Gastos por cobrar'),
    ("3", 'Cambio del valor')
]


class AccountInvoice(models.Model):
    _inherit = 'account.move'

    l10n_co_edi_operation_type = fields.Selection([('10', 'Estandar'),
                                                  ('09', 'AIU'),
                                                  ('11', 'Mandatos'),
                                                  ('12', 'Transporte'),
                                                  ('13', 'Cambiario'),
                                                  ('20', 'Nota Crédito que referencia una factura electrónica'),
                                                  ('20-POS', 'Factura Contingencia PoS - tipo 20'),
                                                  ('22', 'Nota Crédito sin referencia a facturas'),
                                                  ('30', 'Nota Débito que referencia una factura electrónica'),
                                                  ('32', 'Nota Débito sin referencia a facturas'),
                                                  ('23', 'Inactivo: Nota Crédito para facturación electrónica V1 (Decreto 2242)'),
                                                  ('33', 'Inactivo: Nota Débito para facturación electrónica V1 (Decreto 2242)')],
                                                  string="Operation Type", default="10", required=True)
    l10n_co_edi_cufe_cude_ref = fields.Char(string="CUFE/CUDE", readonly=True, copy=False)
    l10n_co_edi_payment_option_id = fields.Many2one('l10n_co_edi.payment.option', string="Payment Option", default=lambda self: self.env.ref('l10n_co_edi_ubl_2_1.payment_option_1', raise_if_not_found=False))
    l10n_co_edi_description_code_credit = fields.Selection(DESCRIPTION_CREDIT_CODE, string="Concepto Nota de Credito")
    l10n_co_edi_is_direct_payment = fields.Boolean("Direct Payment from Colombia", compute="_compute_l10n_co_edi_is_direct_payment")
    l10n_co_edi_description_code_debit = fields.Selection(DESCRIPTION_DEBIT_CODE, string="Concepto Nota de Débito")
    l10n_co_edi_debit_note = fields.Boolean(related="journal_id.l10n_co_edi_debit_note", readonly=True)
    l10n_co_edi_debit_origin_id = fields.Many2one('account.move', string="Documento de referencia de la Nota de Débito",
                                                  help="This is the invoice which needed correction by this debit note.  "
                                                       "We have a field for credit notes, but need one here for its positive counterpart. ")
    l10n_co_edi_type = fields.Selection(selection_add=[
        ('3', 'Documento electrónico de transmisión – tipo 03'),
        ('4', 'Factura electrónica de Venta - tipo 04'),
    ])
    l10n_co_edi_country_code = fields.Char(related='company_id.country_id.code')
    l10n_co_edi_is_support_document = fields.Boolean('Support Document', related='journal_id.l10n_co_edi_is_support_document')

    @api.depends('invoice_date_due', 'date')
    def _compute_l10n_co_edi_is_direct_payment(self):
        for rec in self:
            rec.l10n_co_edi_is_direct_payment = (rec.date == rec.invoice_date_due) and rec.company_id.country_id.code == 'CO'

    @api.onchange('type', 'reversed_entry_id', 'l10n_co_edi_invoice_status', 'l10n_co_edi_cufe_cude_ref')
    def _onchange_type(self):
        for rec in self:
            operation_type = False
            if rec.type == 'out_refund':
                if rec.reversed_entry_id:
                    operation_type = '20'
                else:
                    operation_type = '22'
            else:
                if rec.l10n_co_edi_debit_note:
                    if rec.l10n_co_edi_invoice_status == 'accepted' and not rec.l10n_co_edi_cufe_cude_ref:
                        operation_type = '23'
                    elif rec.l10n_co_edi_debit_origin_id:
                        operation_type = '30'
                    else:
                        operation_type = '32'
            rec.l10n_co_edi_operation_type = operation_type or '10'

    def _l10n_co_edi_get_environment(self):
        if self.company_id.l10n_co_edi_test_mode:
            return '2'
        return '1'

    def _l10n_co_edi_get_partner_type(self, partner_id):
        if partner_id.is_company:
            return '1'
        return '2'

    def _l10n_co_edi_get_edi_type(self):
        if self.type == 'out_refund':
            return "91"
        elif self.type == 'out_invoice' and self.l10n_co_edi_debit_note:
            return "92"
        return "{0:0=2d}".format(int(self.l10n_co_edi_type))

    def _l10n_co_edi_get_edi_description(self):
        if self.type in ('out_refund', 'in_refund'):
            return dict(DESCRIPTION_CREDIT_CODE).get(self.l10n_co_edi_description_code_credit)
        if self.type in ('out_invoice', 'in_invoice') and self.l10n_co_edi_debit_note:
            return dict(DESCRIPTION_DEBIT_CODE).get(self.l10n_co_edi_description_code_debit)

    def _l10n_co_edi_get_edi_description_code(self):
        if self.type in ('out_refund', 'in_refund'):
            return self.l10n_co_edi_description_code_credit
        if self.type in ('out_invoice', 'in_invoice') and self.l10n_co_edi_debit_note:
            return self.l10n_co_edi_description_code_debit

    def _l10n_co_edi_get_validation_time_new_format(self):
        """For the new version, the time format has to include the timezone (-05:00)"""
        validation_time = self.l10n_co_edi_datetime_invoice
        validation_time = pytz.utc.localize(validation_time)

        bogota_tz = pytz.timezone('America/Bogota')
        validation_time = validation_time.astimezone(bogota_tz)
        return validation_time.strftime(DEFAULT_SERVER_TIME_FORMAT) + "-05:00"

    def _l10n_co_edi_get_electronic_invoice_type(self):
        if self.type == 'out_invoice':
            return 'ND' if self.l10n_co_edi_debit_note else 'INVOIC'
        elif self.type == 'in_invoice':
            return 'DS'
        return 'NC'

    def _l10n_co_edi_get_electronic_invoice_type_info(self):
        if self.type == 'out_invoice':
            return 'DIAN 2.1: Nota Débito de Factura Electrónica de Venta' if self.l10n_co_edi_debit_note else 'DIAN 2.1: Factura Electrónica de Venta'
        elif self.type == 'in_invoice':
            return 'DIAN 2.1: documento soporte en adquisiciones efectuadas a no obligados a facturar.'
        elif self.type == 'in_refund':
            return 'DIAN 2.1: Nota de ajuste al documento soporte en adquisiciones efectuadas a sujetos no obligados a expedir factura o documento equivalente'
        return 'DIAN 2.1: Nota Crédito de Factura Electrónica de Venta'

    def _l10n_co_edi_get_delivery_date(self):
        return self.invoice_date + timedelta(1)

    def _l10n_co_edi_get_round_amount(self, amount):
        if abs(amount - float("%.2f" % amount)) > 0.00001:
            return "%.3f" % amount
        return '%.2f' % amount

    def l10n_co_edi_upload_electronic_invoice(self):
        """Some checks already before sending the electronic invoice to Carvajal"""
        to_process = self.filtered(lambda move: move._l10n_co_edi_is_l10n_co_edi_required())
        now = fields.Datetime.now()
        oldest_date = now - timedelta(days=5)
        newest_date = now + timedelta(days=10)
        if to_process:
            for invoice in to_process:
                if invoice.invoice_date and not (oldest_date <= fields.Datetime.to_datetime(invoice.invoice_date) <= newest_date):
                    invoice.message_post(body=_('The issue date can not be older than 5 days or more than 5 days in the future.'))
            if to_process.filtered(lambda m: not m.partner_id.vat):
                raise UserError(_('You can not validate an invoice that has a partner without VAT number'))
            if to_process.filtered(lambda m: not m.partner_id.l10n_co_edi_obligation_type_ids):
                raise UserError(_('All the information on the Customer Fiscal Data section needs to be set'))
            for inv in to_process:
                if (inv.l10n_co_edi_type == '2' and any(l.product_id and not l.product_id.l10n_co_edi_customs_code for l in inv.invoice_line_ids)) or (
                    any(l.product_id and not l.product_id.default_code and not l.product_id.barcode and not l.product_id.unspsc_code_id for l in inv.invoice_line_ids)):
                    raise UserError(_('Every product on a line should at least have a product code (barcode, unspsc, internal) set. '))
            to_process.write({'l10n_co_edi_datetime_invoice': now})
        return super(AccountInvoice, self).l10n_co_edi_upload_electronic_invoice()

    def _l10n_co_edi_prepare_tim_sections(self, taxes_dict, retention, zero_taxes=None):
        @lru_cache(maxsize=None)
        def _get_conversion_rate(from_currency, to_currency, company, date):
            if from_currency == to_currency:
                return 1
            currency_rates = (from_currency + to_currency)._get_rates(company, date)
            return currency_rates.get(to_currency.id) / currency_rates.get(from_currency.id)

        def _convert(from_currency, from_amount, to_currency, company, date):
            return to_currency.round(from_amount * _get_conversion_rate(from_currency, to_currency, company, date))

        new_taxes_dict = defaultdict(list)
        zero_taxes = zero_taxes or {}
        for tax_code, values in taxes_dict.items():
            tim = {
                'TIM_1': bool(retention),
                'TIM_2': 0.0,
                'TIM_3': self.currency_id.name,
                'TIM_4': 0.0,
                'TIM_5': self.currency_id.name,
                'IMPS': [],
            }
            for rec in values:
                imp = {
                    'IMP_1': tax_code,
                    'IMP_2': (
                        abs((rec.amount_currency or rec.balance) * 100 / 15)
                        if rec.tax_line_id.l10n_co_edi_type.code == '05' else
                        _convert(rec.company_id.currency_id, rec.tax_base_amount, rec.currency_id or rec.company_id.currency_id, rec.company_id, rec.move_id.invoice_date)
                    ),
                    'IMP_3': self.currency_id.name,
                    'IMP_4': abs(rec.amount_currency or rec.balance),
                    'IMP_5': self.currency_id.name,
                }
                if rec.tax_line_id.amount_type == 'fixed':
                    imp.update({
                        'IMP_6': '',
                        'IMP_7': 1,
                        'IMP_8': 'BO' if rec.tax_line_id.l10n_co_edi_type.code == '22' else '94',
                        'IMP_9': rec.tax_line_id.amount,
                        'IMP_10': self.currency_id.name,
                    })
                else:
                    imp.update({
                        'IMP_6': 15.0 if rec.tax_line_id.l10n_co_edi_type.code == '05' else abs(rec.tax_line_id.amount),
                        'IMP_7': '',
                        'IMP_8': '',
                        'IMP_9': '',
                        'IMP_10': '',
                    })
                    tim['TIM_4'] += (imp['IMP_6'] / 100.0 * imp['IMP_2']) - imp['IMP_4']
                tim['TIM_2'] += imp['IMP_4']
                tim['IMPS'].append(imp)
            if zero_taxes.get(tax_code):
                tim['IMPS'].append({
                    'IMP_1': tax_code,
                    'IMP_2': zero_taxes[tax_code],
                    'IMP_3': self.currency_id.name,
                    'IMP_4': 0,
                    'IMP_5': self.currency_id.name,
                    'IMP_6': 0,
                    'IMP_7': '',
                    'IMP_8': '',
                    'IMP_9': '',
                    'IMP_10': '',
                })
                zero_taxes.pop(tax_code)
            new_taxes_dict[tax_code] = tim
        for tax_code, values in zero_taxes.items():
            new_taxes_dict[tax_code] = {
                'TIM_1': bool(retention),
                'TIM_2': 0,
                'TIM_3': self.currency_id.name,
                'TIM_4': 0,
                'TIM_5': self.currency_id.name,
                'IMPS': [{
                    'IMP_1': tax_code,
                    'IMP_2': zero_taxes[tax_code],
                    'IMP_3': self.currency_id.name,
                    'IMP_4': 0,
                    'IMP_5': self.currency_id.name,
                    'IMP_6': 0,
                    'IMP_7': '',
                    'IMP_8': '',
                    'IMP_9': '',
                    'IMP_10': ''
                }]
            }
        return new_taxes_dict

    def _l10n_co_edi_generate_xml(self):
        '''Renders the XML that will be sent to Carvajal.'''
        # generate xml with strings in language of customer
        self = self.with_context(lang=self.partner_id.lang)

        move_lines_with_tax_type = self.line_ids.filtered('tax_line_id.l10n_co_edi_type')

        ovt_tax_codes = ('01C', '02C', '03C')
        ovt_taxes = move_lines_with_tax_type.filtered(lambda move: move.tax_line_id.l10n_co_edi_type.code in ovt_tax_codes).mapped('tax_line_id')

        invoice_type_to_ref_1 = {
            'out_invoice': 'IV',
            'out_refund': 'NC',
        }
        tax_types = self.mapped('line_ids.tax_ids.l10n_co_edi_type')

        taxes_amount_dict = {}
        exempt_tax_dict = {}
        tax_group_covered_goods = self.env.ref('l10n_co.tax_group_covered_goods', raise_if_not_found=False)
        zero_taxes = defaultdict(float)
        for line in self.invoice_line_ids:
            price_unit = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            taxes = line.tax_ids.with_context(force_sign=line.move_id._get_tax_force_sign()).compute_all(price_unit, quantity=line.quantity, currency=line.currency_id,
                                             product=line.product_id, partner=line.partner_id)
            taxes_amount_dict[line.id] = []

            for tax in taxes['taxes']:
                tax_rec = self.env['account.tax'].browse(tax['id'])
                if tax['amount'] == 0.0:
                    zero_taxes[tax_rec.l10n_co_edi_type.code] += tax['base']
                taxes_amount_dict[line.id].append({'base': "%.2f" % tax['base'],
                                                   'tax': tax['amount'],
                                                   'code': tax_rec.l10n_co_edi_type.code,
                                                   'retention': tax_rec.l10n_co_edi_type.retention,
                                                   'rate': tax_rec.amount,
                                                   'amount_type': tax_rec.amount_type})
            if tax_group_covered_goods and tax_group_covered_goods in line.mapped('tax_ids.tax_group_id'):
                exempt_tax_dict[line.id] = True

        retention_lines = move_lines_with_tax_type.filtered(
            lambda move: move.tax_line_id.l10n_co_edi_type.retention)
        retention_lines_dict = {}  # TODO remove, kept for stable policy
        retention_lines_listdict = defaultdict(list)
        for line in retention_lines:
            retention_lines_listdict[line.tax_line_id.l10n_co_edi_type.code].append(line)
            retention_lines_dict[line.tax_line_id.l10n_co_edi_type] = line
        retention_lines_dict_new = self._l10n_co_edi_prepare_tim_sections(retention_lines_listdict, True)

        regular_lines = move_lines_with_tax_type - retention_lines
        regular_lines_dict = {}  # TODO remove, kept for stable policy
        regular_lines_listdict = defaultdict(list)
        for line in regular_lines:
            regular_lines_listdict[line.tax_line_id.l10n_co_edi_type.code].append(line)
            regular_lines_dict[line.tax_line_id.l10n_co_edi_type] = line
        regular_lines_dict_new = self._l10n_co_edi_prepare_tim_sections(regular_lines_listdict, False, zero_taxes)

        # The rate should indicate how many pesos is one foreign currency
        currency_rate = "%.2f" % (1.0 / self.currency_id.with_context(date=self.invoice_date or fields.Date.today()).rate)

        withholding_amount = '%.2f' % (self.amount_untaxed + sum(self.line_ids.filtered(lambda move: move.tax_line_id and not move.tax_line_id.l10n_co_edi_type.retention).mapped('price_total')))

        xml_content = self._l10n_co_edi_get_electronic_invoice_template().render({
            'invoice': self,
            'company_partner': self.company_id.partner_id,
            'sales_partner': self.user_id,
            'invoice_partner': self.partner_id.commercial_partner_id,
            'retention_lines_dict': retention_lines_dict,
            'retention_lines_dict_new': retention_lines_dict_new,
            'regular_lines_dict': regular_lines_dict,
            'regular_lines_dict_new': regular_lines_dict_new,
            'tax_types': tax_types,
            'exempt_tax_dict': exempt_tax_dict,
            'currency_rate': currency_rate,
            'shipping_partner': self.env['res.partner'].browse(self._get_invoice_delivery_partner_id()),
            'invoice_type_to_ref_1': invoice_type_to_ref_1,
            'ovt_taxes': ovt_taxes,
            'float_compare': float_compare,
            'notas': self._l10n_co_edi_get_notas(),
            'taxes_amount_dict': taxes_amount_dict,
            'withholding_amount': withholding_amount,
            '_l10n_co_edi_get_round_amount': self._l10n_co_edi_get_round_amount,
        })
        return '<?xml version="1.0" encoding="utf-8"?>'.encode() + xml_content

    def _l10n_co_edi_get_electronic_invoice_template(self):
        if self.type in ('in_invoice', 'in_refund'):
            return self.env.ref('l10n_co_edi_ubl_2_1.electronic_invoice_vendor_document_xml')
        return self.env.ref('l10n_co_edi_ubl_2_1.electronic_invoice_xml')

    def _l10n_co_edi_get_carvajal_type(self):
        if self.type == 'in_invoice':
            return 'DS'
        elif self.type == 'in_refund':
            return 'NS'
        return super()._l10n_co_edi_get_carvajal_type()

    def _l10n_co_edi_is_l10n_co_edi_required(self):
        self.ensure_one()
        if self.type in ('in_invoice', 'in_refund'):
            return self.env.ref('l10n_co_edi_ubl_2_1.electronic_invoice_vendor_document_xml', False) and self.company_id.country_id == self.env.ref('base.co') and self.l10n_co_edi_is_support_document
        return super()._l10n_co_edi_is_l10n_co_edi_required()

    def l10n_co_edi_download_electronic_invoice(self):
        """ Method called by the user to download the response from the processing of the invoice by the DIAN
        and also get the CUFE signature out of that file
        """
        invoice_download_msg, attachments = super(AccountInvoice, self).l10n_co_edi_download_electronic_invoice()
        if attachments:
            with tools.osutil.tempdir() as file_dir:
                zip_ref = zipfile.ZipFile(io.BytesIO(attachments[0][1]))
                zip_ref.extractall(file_dir)
                xml_file = [f for f in listdir(file_dir) if f.endswith('.xml')]
                if xml_file:
                    content = xml.dom.minidom.parseString(zip_ref.read(xml_file[0]))
                    element = content.getElementsByTagName('cbc:UUID')
                    if element:
                        self.l10n_co_edi_cufe_cude_ref = element[0].childNodes[0].nodeValue
        return (invoice_download_msg, attachments)

    def _l10n_co_edi_get_notas(self):
        # Need to update the element in array on index with number 4.
        notas = super(AccountInvoice, self)._l10n_co_edi_get_notas()
        notas.pop(4)
        notas.insert(4, '7.- %s' % (self.company_id.website))
        return notas

    def _l10n_co_edi_get_company_address(self, partner):
        """
        Function forms address of the company avoiding duplicity. contact_address attribute holds the complete address
        of company, which should not be used.
        Information like city, state which is already sent in other tags should be excluded from the company's address.
        """
        return '%s %s' % (partner.street or '', partner.street2 or '')


class AccountInvoiceLine(models.Model):
    _inherit = 'account.move.line'

    def _l10n_co_edi_get_product_code(self):
        """
        For identifying products, different standards can be used.  If there is a barcode, we take that one, because
        normally in the GTIN standard it will be the most specific one.  Otherwise, we will check the
        :return: (standard, product_code)
        """
        self.ensure_one()
        if self.product_id:
            if self.move_id.l10n_co_edi_type == '2':
                if not self.product_id.l10n_co_edi_customs_code:
                    raise UserError(_('Exportation invoices require custom code in all the products, please fill in this information before validating the invoice'))
                return (self.product_id.l10n_co_edi_customs_code, '020', 'Partida Alanceraria')
            if self.product_id.barcode:
                return (self.product_id.barcode, '010', 'GTIN')
            elif self.product_id.unspsc_code_id:
                return (self.product_id.unspsc_code_id.code, '001', 'UNSPSC')
            elif self.product_id.default_code:
                return (self.product_id.default_code, '999', 'Estándar de adopción del contribuyente')

        return ('1010101', '001', '')

    def _l10n_co_edi_get_iae3_value(self, product_code):
        value = {
            '010': '9',
            '001': '10',
        }
        return value.get(product_code, '')
