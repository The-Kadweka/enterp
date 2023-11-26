# -*- coding: utf-8 -*-

import base64
import logging
import re
from odoo import api, exceptions, fields, models, _
from odoo.tools import pycompat
from odoo.addons.iap import jsonrpc
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)

PARTNER_REMOTE_URL = 'https://partner-autocomplete.odoo.com/iap/partner_autocomplete'
CLIENT_OCR_VERSION = 120

def to_float(text):
    """format a text to try to find a float in it. Ex: 127,00  320.612,8  15.9"""
    t_no_space = text.replace(" ", "")
    char = ""
    for c in t_no_space:
        if c in ['.', ',']:
            char = c
    if char == ",":
        t_no_space = t_no_space.replace(".", "")
        t_no_space = t_no_space.replace(",", ".")
    elif char == ".":
        t_no_space = t_no_space.replace(",", "")
    try:
        return float(t_no_space)
    except (AttributeError, ValueError):
        return None 

#List of result id that can be sent by iap-extract
SUCCESS = 0
NOT_READY = 1
ERROR_INTERNAL = 2
ERROR_NOT_ENOUGH_CREDIT = 3
ERROR_DOCUMENT_NOT_FOUND = 4
ERROR_NO_DOCUMENT_NAME = 5
ERROR_UNSUPPORTED_IMAGE_FORMAT = 6
ERROR_FILE_NAMES_NOT_MATCHING = 7


class AccountInvoiceExtractionWords(models.Model):

    _name = "account.invoice_extract.words"
    _description = "Extracted words from invoice scan"

    invoice_id = fields.Many2one("account.invoice", help="Invoice id")
    field = fields.Char()
    selected_status = fields.Integer("Invoice extract selected status.",
        help="0 for 'not selected', 1 for ocr choosed and 2 for ocr selected but not choosed by user")
    user_selected = fields.Boolean()
    word_text = fields.Char()
    word_page = fields.Integer()
    word_box_midX = fields.Float()
    word_box_midY = fields.Float()
    word_box_width = fields.Float()
    word_box_height = fields.Float()
    word_box_angle = fields.Float()
    

class AccountInvoice(models.Model):

    _name = "account.invoice"
    _inherit = ['account.invoice']

    def _compute_can_show_send_resend(self, record):
        can_show = True
        if record.company_id.extract_show_ocr_option_selection == 'no_send':
            can_show = False
        if record.state not in 'draft':
            can_show = False
        if record.type in ["out_invoice", "out_refund"]:
            can_show = False
        if record.message_main_attachment_id is None or len(record.message_main_attachment_id) == 0:
            can_show = False
        return can_show

    @api.depends('state', 'extract_state', 'message_main_attachment_id')
    def _compute_show_resend_button(self):
        for record in self:
            record.extract_can_show_resend_button = record._compute_can_show_send_resend(record)
            if record.extract_state not in ['error_status', 'not_enough_credit', 'module_not_up_to_date']:
                record.extract_can_show_resend_button = False

    @api.depends('state', 'extract_state', 'message_main_attachment_id')
    def _compute_show_send_button(self):
        for record in self:
            record.extract_can_show_send_button = record._compute_can_show_send_resend(record)
            if record.extract_state not in ['no_extract_requested']:
                record.extract_can_show_send_button = False

    extract_state = fields.Selection([('no_extract_requested', 'No extract requested'),
                            ('not_enough_credit', 'Not enough credit'),
                            ('error_status', 'An error occured'),
                            ('waiting_extraction', 'Waiting extraction'),
                            ('extract_not_ready', 'waiting extraction, but it is not ready'),
                            ('waiting_validation', 'Waiting validation'),
                            ('done', 'Completed flow')],
                            'Extract state', default='no_extract_requested', required=True, copy=False)
    extract_remoteid = fields.Integer("Id of the request to IAP-OCR", default="-1", help="Invoice extract id", copy=False)
    extract_word_ids = fields.One2many("account.invoice_extract.words", inverse_name="invoice_id", copy=False)

    extract_can_show_resend_button = fields.Boolean("Can show the ocr resend button", compute=_compute_show_resend_button)
    extract_can_show_send_button = fields.Boolean("Can show the ocr send button", compute=_compute_show_send_button)

    @api.multi
    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, **kwargs):
        """When a message is posted on an account.invoice, send the attachment to iap-ocr if
        the res_config is on "auto_send" and if this is the first attachment."""
        res = super(AccountInvoice, self).message_post(**kwargs)
        if self.company_id.extract_show_ocr_option_selection == 'auto_send':
            account_token = self.env['iap.account'].get('invoice_ocr')
            # We need to be sure that an account token exists for partner_autocomplete too to avoid a commit in an 'update status' flow.
            self.env['iap.account'].get('partner_autocomplete')
            for record in self:
                if record.type in ["out_invoice", "out_refund"]:
                    return res
                if record.extract_state == "no_extract_requested":
                    attachments = res.attachment_ids
                    if attachments:
                        endpoint = self.env['ir.config_parameter'].sudo().get_param(
                            'account_invoice_extract_endpoint', 'https://iap-extract.odoo.com') + '/iap/invoice_extract/parse'
                        user_infos = {
                            'user_company_VAT': record.company_id.vat,
                            'user_company_name': record.company_id.name,
                            'user_company_country_code': record.company_id.country_id.code,
                            'user_lang': self.env.user.lang,
                            'user_email': self.env.user.email,
                        }
                        #this line contact iap to create account if this is the first request. This allow iap to give free credits if the database is elligible
                        self.env['iap.account'].get_credits('invoice_ocr')
                        params = {
                            'account_token': account_token.account_token,
                            'version': CLIENT_OCR_VERSION,
                            'dbuuid': self.env['ir.config_parameter'].sudo().get_param('database.uuid'),
                            'documents': [x.datas.decode('utf-8') for x in attachments],
                            'file_names': [x.datas_fname for x in attachments],
                            'user_infos': user_infos,
                            
                        }
                        try:
                            result = jsonrpc(endpoint, params=params)
                            if result['status_code'] == SUCCESS:
                                record.extract_state = 'waiting_extraction'
                                record.extract_remoteid = result['document_id']
                            elif result['status_code'] == ERROR_NOT_ENOUGH_CREDIT:
                                record.extract_state = 'not_enough_credit'
                            else:
                                record.extract_state = 'error_status'
                        except AccessError:
                            record.extract_state = 'error_status'
        return res

    def retry_ocr(self):
        """Retry to contact iap to submit the first attachment in the chatter"""
        if self.company_id.extract_show_ocr_option_selection == 'no_send':
            return False
        attachments = self.message_main_attachment_id
        if attachments and attachments.exists() and self.extract_state in ['no_extract_requested', 'not_enough_credit', 'error_status', 'module_not_up_to_date']:
            account_token = self.env['iap.account'].get('invoice_ocr')
            # We need to be sure that an account token exists for partner_autocomplete too to avoid a commit in an 'update status' flow.
            self.env['iap.account'].get('partner_autocomplete')
            endpoint = self.env['ir.config_parameter'].sudo().get_param(
                'account_invoice_extract_endpoint', 'https://iap-extract.odoo.com')  + '/iap/invoice_extract/parse'
            user_infos = {
                'user_company_VAT': self.company_id.vat,
                'user_company_name': self.company_id.name,
                'user_company_country_code': self.company_id.country_id.code,
                'user_lang': self.env.user.lang,
                'user_email': self.env.user.email,
            }
            #this line contact iap to create account if this is the first request. This allow iap to give free credits if the database is elligible
            self.env['iap.account'].get_credits('invoice_ocr')
            params = {
                'account_token': account_token.account_token,
                'version': CLIENT_OCR_VERSION,
                'dbuuid': self.env['ir.config_parameter'].sudo().get_param('database.uuid'),
                'documents': [x.datas.decode('utf-8') for x in attachments], 
                'file_names': [x.datas_fname for x in attachments],
                'user_infos': user_infos,
            }
            try:
                result = jsonrpc(endpoint, params=params)
                if result['status_code'] == SUCCESS:
                    self.extract_state = 'waiting_extraction'
                    self.extract_remoteid = result['document_id']
                elif result['status_code'] == ERROR_NOT_ENOUGH_CREDIT:
                    self.extract_state = 'not_enough_credit'
                else:
                    self.extract_state = 'error_status'
                    _logger.warning('There was an issue while doing the OCR operation on this file. Error: -1')

            except AccessError:
                self.extract_state = 'error_status'

    @api.multi
    def get_validation(self, field):
        """
        return the text or box corresponding to the choice of the user.
        If the user selected a box on the document, we return this box, 
        but if he entered the text of the field manually, we return only the text, as we 
        don't know which box is the right one (if it exists)
        """
        selected = self.env["account.invoice_extract.words"].search([("invoice_id", "=", self.id), ("field", "=", field), ("user_selected", "=", True)])
        if not selected.exists():
            selected = self.env["account.invoice_extract.words"].search([("invoice_id", "=", self.id), ("field", "=", field), ("selected_status", "=", 1)], limit=1)
        return_box = {}
        if selected.exists():
            return_box["box"] = [selected.word_text, selected.word_page, selected.word_box_midX, 
                selected.word_box_midY, selected.word_box_width, selected.word_box_height, selected.word_box_angle]
        #now we have the user or ocr selection, check if there was manual changes

        text_to_send = {}
        if field == "total":
            text_to_send["content"] = self.amount_total
        elif field == "subtotal":
            text_to_send["content"] = self.amount_untaxed
        elif field == "global_taxes_amount":
            text_to_send["content"] = self.amount_tax
        elif field == "global_taxes":
            text_to_send["content"] = [{
                'amount': tax.amount,
                'tax_amount': tax.tax_id.amount,
                'tax_amount_type': tax.tax_id.amount_type,
                'tax_price_include': tax.tax_id.price_include} for tax in self.tax_line_ids]
        elif field == "date":
            text_to_send["content"] = str(self.date_invoice)
        elif field == "due_date":
            text_to_send["content"] = str(self.date_due)
        elif field == "invoice_id":
            text_to_send["content"] = self.reference
        elif field == "supplier":
            text_to_send["content"] = self.partner_id.name
        elif field == "VAT_Number":
            text_to_send["content"] = self.partner_id.vat
        elif field == "currency":
            text_to_send["content"] = self.currency_id.name
        elif field == "invoice_lines":
            text_to_send = {'lines': []}
            for il in self.invoice_line_ids:
                line = {
                    "description": il.name,
                    "quantity": il.quantity,
                    "unit_price": il.price_unit,
                    "product": il.product_id.id,
                    "taxes_amount": il.price_tax,
                    "taxes": [{
                        'amount': tax.amount,
                        'type': tax.amount_type,
                        'price_include': tax.price_include} for tax in il.invoice_line_tax_ids],
                    "subtotal": il.price_subtotal,
                    "total": il.price_total
                }
                text_to_send['lines'].append(line)
        else:
            return None
        
        return_box.update(text_to_send)
        return return_box

    @api.multi
    def invoice_validate(self):
        """On the validation of an invoice, send the differents corrected fields to iap to improve
        the ocr algorithm"""
        res = super(AccountInvoice, self).invoice_validate()
        for record in self:
            if record.type in ["out_invoice", "out_refund"]:
                return res
            if record.extract_state == 'waiting_validation':
                endpoint = self.env['ir.config_parameter'].sudo().get_param(
                    'account_invoice_extract_endpoint', 'https://iap-extract.odoo.com') + '/iap/invoice_extract/validate'
                values = {
                    'total': record.get_validation('total'),
                    'subtotal': record.get_validation('subtotal'),
                    'global_taxes': record.get_validation('global_taxes'),
                    'global_taxes_amount': record.get_validation('global_taxes_amount'),
                    'date': record.get_validation('date'),
                    'due_date': record.get_validation('due_date'),
                    'invoice_id': record.get_validation('invoice_id'),
                    'partner': record.get_validation('supplier'),
                    'VAT_Number': record.get_validation('VAT_Number'),
                    'currency': record.get_validation('currency'),
                    'merged_lines': not (self.env['ir.config_parameter'].sudo().get_param('account_invoice_extract.no_merging_lines_by_taxes') != 'False'),
                    'invoice_lines': record.get_validation('invoice_lines')
                }
                params = {
                    'document_id': record.extract_remoteid, 
                    'version': CLIENT_OCR_VERSION,
                    'values': values
                }
                try:
                    jsonrpc(endpoint, params=params)
                    record.extract_state = 'done'
                except AccessError:
                    pass
        #we don't need word data anymore, we can delete them
        self.mapped('extract_word_ids').unlink()
        return res

    @api.multi
    def get_boxes(self):
        return [{
            "id": data.id,
            "feature": data.field, 
            "text": data.word_text, 
            "selected_status": data.selected_status, 
            "user_selected": data.user_selected,
            "page": data.word_page,
            "box_midX": data.word_box_midX, 
            "box_midY": data.word_box_midY, 
            "box_width": data.word_box_width, 
            "box_height": data.word_box_height,
            "box_angle": data.word_box_angle} for data in self.extract_word_ids]

    @api.multi
    def remove_user_selected_box(self, id):
        """Set the selected box for a feature. The id of the box indicates the concerned feature.
        The method returns the text that can be set in the view (possibly different of the text in the file)"""
        self.ensure_one()
        word = self.env["account.invoice_extract.words"].browse(int(id))
        to_unselect = self.env["account.invoice_extract.words"].search([("invoice_id", "=", self.id), \
            ("field", "=", word.field), '|', ("user_selected", "=", True), ("selected_status", "!=", 0)])
        user_selected_found = False
        for box in to_unselect:
            if box.user_selected:
                user_selected_found = True
                box.user_selected = False
        ocr_new_value = 0
        new_word = None
        if user_selected_found:
            ocr_new_value = 1
        for box in to_unselect:
            if box.selected_status != 0:
                box.selected_status = ocr_new_value
                if ocr_new_value != 0:
                    new_word = box
        word.user_selected = False
        if new_word is None:
            if word.field in ["VAT_Number", "supplier", "currency"]:
                return 0
            return ""
        if new_word.field in ["date", "due_date", "invoice_id", "currency"]:
            pass
        if new_word.field == "VAT_Number":
            partner_vat = self.env["res.partner"].search([("vat", "=", new_word.word_text)], limit=1)
            if partner_vat.exists():
                return partner_vat.id
            return 0
        if new_word.field == "supplier":
            partner_names = self.env["res.partner"].search([("name", "ilike", new_word.word_text)])
            if partner_names.exists():
                partner = min(partner_names, key=len)
                return partner.id
            else:
                partners = {}
                for single_word in new_word.word_text.split(" "):
                    partner_names = self.env["res.partner"].search([("name", "ilike", single_word)], limit=30)
                    for partner in partner_names:
                        partners[partner.id] = partners[partner.id] + 1 if partner.id in partners else 1
                if len(partners) > 0:
                    key_max = max(partners.keys(), key=(lambda k: partners[k]))
                    return key_max
            return 0
        return new_word.word_text

    @api.multi
    def set_user_selected_box(self, id):
        """Set the selected box for a feature. The id of the box indicates the concerned feature.
        The method returns the text that can be set in the view (possibly different of the text in the file)"""
        self.ensure_one()
        word = self.env["account.invoice_extract.words"].browse(int(id))
        to_unselect = self.env["account.invoice_extract.words"].search([("invoice_id", "=", self.id), ("field", "=", word.field), ("user_selected", "=", True)])
        for box in to_unselect:
            box.user_selected = False
        ocr_boxes = self.env["account.invoice_extract.words"].search([("invoice_id", "=", self.id), ("field", "=", word.field), ("selected_status", "=", 1)])
        for box in ocr_boxes:
            if box.selected_status != 0:
                box.selected_status = 2
        word.user_selected = True
        if word.field == "date":
            pass
        if word.field == "due_date":
            pass
        if word.field == "invoice_id":
            pass
        if word.field == "currency":
            text = word.word_text
            currency = None
            currencies = self.env["res.currency"].search([])
            for curr in currencies:
                if text == curr.currency_unit_label:
                    currency = curr
                if text == curr.name or text == curr.symbol:
                    currency = curr
            if currency:
                return currency.id
            return self.currency_id.id
        if word.field == "VAT_Number":
            partner_vat = self.env["res.partner"].search([("vat", "=", word.word_text)], limit=1)
            if partner_vat.exists():
                return partner_vat.id
            else:
                vat = word.word_text
                url = '%s/enrich' % PARTNER_REMOTE_URL
                params = {
                    'db_uuid': self.env['ir.config_parameter'].sudo().get_param('database.uuid'),
                    'account_token': self.env['iap.account'].get('partner_autocomplete').account_token,
                    'country_code': self.company_id.country_id.code,
                    'vat': vat,
                }
                try:
                    response = jsonrpc(url=url, params=params)
                except Exception as exception:
                    _logger.error('Check VAT error: %s' % str(exception))
                    return 0

                if response and response.get('company_data'):
                    country_id = self.env['res.country'].search([('code', '=', response.get('company_data').get('country_code',''))])
                    state_id = self.env['res.country.state'].search([('name', '=', response.get('company_data').get('state_name',''))])
                    resp_values = response.get('company_data')
                    values = {
                        'name': resp_values.get('name', ''),
                        'partner_gid': resp_values.get('partner_gid', ''),
                        'vat': resp_values.get('vat', ''),
                        'bank_ids': resp_values.get('bank_ids', ''),
                        'street': resp_values.get('street', ''),
                        'city': resp_values.get('city', ''),
                        'zip': resp_values.get('zip', ''),
                        'state_id': state_id and state_id.id,
                        'country_id': country_id and country_id.id,
                        'phone': resp_values.get('phone', ''),
                        'email': resp_values.get('email', ''),
                        'supplier': True,
                        'customer': False,
                        'is_company': True,
                    }
                    new_partner = self.env["res.partner"].create(values)
                    return new_partner.id
            return 0

        if word.field == "supplier":
            return self.find_partner_id_with_name(word.word_text)
        return word.word_text

    def _get_partner_fields(self): 
        return ['name', 'vat', 'street', 'city', 'zip']
        
    @api.multi
    def _set_vat(self, text):
        partner_vat = self.env["res.partner"].search([("vat", "=", text)], limit=1)
        if partner_vat.exists():
            self.partner_id = partner_vat
            self._onchange_partner_id()
            return True
        return False

    @api.multi
    def find_partner_id_with_name(self, partner_name):
        if not partner_name:
            return 0
        partner_names = self.env["res.partner"].search([("name", "ilike", partner_name)])
        if partner_names.exists():
            partner = min(partner_names, key=len)
            return partner.id
        else:
            partners = {}
            for single_word in [word for word in re.findall(r"[\w]+", partner_name) if len(word) >= 4]:
                partner_names = self.env["res.partner"].search([("name", "ilike", single_word)], limit=30)
                for partner in partner_names:
                    partners[partner.id] = partners[partner.id] + 1 if partner.id in partners else 1
            if len(partners) > 0:
                key_max = max(partners.keys(), key=(lambda k: partners[k]))
                return key_max
        return 0

    @api.multi
    def set_field_with_text(self, field, text):
        """DEPRECATED: the 120 version don't use this method anymore, but we keep it in stable version for compatibility"""
        """change a field with the data present in the text parameter"""
        self.ensure_one()
        if field == "total":
            if len(self.invoice_line_ids) == 1:
                self.invoice_line_ids[0].price_unit = to_float(text)
                self.invoice_line_ids[0].price_total = to_float(text)
            elif len(self.invoice_line_ids) == 0:
                self.invoice_line_ids.with_context(set_default_account=True, journal_id=self.journal_id.id).create({'name': "/",
                    'invoice_id': self.id,
                    'price_unit': to_float(text),
                    'price_total': to_float(text),
                    'quantity': 1,
                    })
                if getattr(self.invoice_line_ids[0],'_predict_account', False):
                    predicted_account_id = self.invoice_line_ids[0]._predict_account(text, self.invoice_line_ids[0].partner_id)
                    # We only change the account if we manage to predict its value
                    if predicted_account_id:
                        self.invoice_line_ids[0].account_id = predicted_account_id
                self.invoice_line_ids[0]._set_taxes()

        if field == "description":
            if len(self.invoice_line_ids) == 1:
                self.invoice_line_ids[0].name = text
                if getattr(self.invoice_line_ids[0],'_predict_account', False):
                    predicted_account_id = self.invoice_line_ids[0]._predict_account(text, self.invoice_line_ids[0].partner_id)
                    # We only change the account if we manage to predict its value
                    if predicted_account_id:
                        self.invoice_line_ids[0].account_id = predicted_account_id
                self.invoice_line_ids[0]._set_taxes()

            elif len(self.invoice_line_ids) == 0:
                self.invoice_line_ids.with_context(set_default_account=True, journal_id=self.journal_id.id).create({'name': text,
                    'invoice_id': self.id,
                    'price_unit': 0,
                    'price_total': 0,
                    'quantity': 1,
                    })
                if getattr(self.invoice_line_ids[0],'_predict_account', False):
                    predicted_account_id = self.invoice_line_ids[0]._predict_account(text, self.invoice_line_ids[0].partner_id)
                    # We only change the account if we manage to predict its value
                    if predicted_account_id:
                        self.invoice_line_ids[0].account_id = predicted_account_id
                self.invoice_line_ids[0]._set_taxes()

        if field == "date":
            self.date_invoice = text
        if field == "due_date":
            self.date_due = text
        if field == "invoice_id":
            self.reference = text.strip()
        if field == "currency" and self.user_has_groups('base.group_multi_currency'):
            text = text.strip()
            currency = None
            currencies = self.env["res.currency"].search([])
            for curr in currencies:
                if text == curr.currency_unit_label:
                    currency = curr
                if text.replace(" ", "") == curr.name or text.replace(" ", "") == curr.symbol:
                    currency = curr
            if currency:
                self.currency_id = currency.id
        #partner
        partner_found = False
        if field == "VAT_Number":
            partner_vat = self.env["res.partner"].search([("vat", "=", text.replace(" ", ""))], limit=1)
            if partner_vat.exists():
                self.partner_id = partner_vat
                self._onchange_partner_id()
                partner_found = True
        if not partner_found and field == "supplier":
            partner_id = self.find_partner_id_with_name(text)
            if partner_id != 0:
                self.partner_id = partner_id
                self._onchange_partner_id()

    @api.multi
    def _set_supplier(self, supplier_ocr, vat_number_ocr):
        self.ensure_one()
        if not self.partner_id:
            partner_id = False
            if vat_number_ocr != "":
                partner_id =  self.env["res.partner"].search([("vat", "=", vat_number_ocr)], limit=1).id
            if not partner_id:
                partner_id = self.find_partner_id_with_name(supplier_ocr)
            if partner_id:
                self.write({'partner_bank_id': False, 'partner_id': partner_id})
                self._onchange_partner_id()

    @api.multi
    def _set_invoice_lines(self, invoice_lines, subtotal_ocr):
        self.ensure_one()
        invoice_lines_to_create = []
        taxes_found = {}
        line_tax_type = self.env['ir.config_parameter'].sudo().get_param('account.show_line_subtotals_tax_selection')
        if self.env['ir.config_parameter'].sudo().get_param('account_invoice_extract.no_merging_lines_by_taxes'):
            aggregated_lines = {}
            for il in invoice_lines:
                description = il['description']['selected_value']['content'] if 'description' in il else None
                total = il['total']['selected_value']['content'] if 'total' in il else 0.0
                subtotal = il['subtotal']['selected_value']['content'] if 'subtotal' in il else total
                taxes = [value['content'] for value in il['taxes']['selected_values']] if 'taxes' in il else []
                taxes_type_ocr = [value['amount_type'] if 'amount_type' in value else 'percent' for value in il['taxes']['selected_values']] if 'taxes' in il else []
                keys = []
                for taxes, taxes_type in pycompat.izip(taxes, taxes_type_ocr):
                    if taxes != 0.0:
                        if (taxes, taxes_type) not in taxes_found:
                            related_documents = self.env['account.invoice'].search([('state', '!=', 'draft'), ('type', '=', self.type), ('partner_id', '=', self.partner_id.id)])
                            lines = related_documents.mapped('invoice_line_ids')
                            taxes_ids = related_documents.mapped('invoice_line_ids.invoice_line_tax_ids')
                            taxes_ids.filtered(lambda tax: tax.amount == taxes and tax.amount_type == taxes_type and tax.type_tax_use == 'purchase')
                            taxes_by_document = []
                            for tax in taxes_ids:
                                taxes_by_document.append((tax, lines.filtered(lambda line: tax in line.invoice_line_tax_ids)))
                            if len(taxes_by_document) != 0:
                                taxes_found[(taxes, taxes_type)] = max(taxes_by_document, key=lambda tax: len(tax[1]))[0].id
                                keys.append(taxes_found[(taxes, taxes_type)])
                            else:
                                taxes_record = self.env['account.tax'].search([('amount', '=', taxes), ('amount_type', '=', taxes_type), ('type_tax_use', '=', 'purchase'), ('company_id', '=', self.company_id.id)])
                                taxes_records_setting_based = taxes_record.filtered(lambda r: not r.price_include if line_tax_type == 'tax_excluded' else r.price_include)
                                if taxes_records_setting_based:
                                    taxes_found[(taxes, taxes_type)] = taxes_records_setting_based[0].id
                                    keys.append(taxes_found[(taxes, taxes_type)])
                                elif taxes_record:
                                    taxes_found[(taxes, taxes_type)] = taxes_record[0].id
                                    keys.append(taxes_found[(taxes, taxes_type)])
                        else:
                            keys.append(taxes_found[(taxes, taxes_type)])

                if tuple(keys) not in aggregated_lines:
                    aggregated_lines[tuple(keys)] = {'subtotal': subtotal, 'description': [description] if description is not None else []}
                else:
                    aggregated_lines[tuple(keys)]['subtotal'] += subtotal
                    if description is not None:
                        aggregated_lines[tuple(keys)]['description'].append(description)

            # if there is only one line after aggregating the lines, use the total found by the ocr as it is less error-prone
            if len(aggregated_lines) == 1:
                aggregated_lines[list(aggregated_lines.keys())[0]]['subtotal'] = subtotal_ocr

            for taxes_ids, il in aggregated_lines.items():
                vals = {
                    'name': "\n".join(il['description']) if len(il['description']) > 0 else "/",
                    'invoice_id': self.id,
                    'price_unit': il['subtotal'],
                    'quantity': 1.0,
                }
                tax_ids = []
                for tax in taxes_ids:
                    tax_ids.append((4, tax))
                if tax_ids:
                    tax = self.env['account.tax'].browse(tax_ids[0][1])
                    if tax.price_include:
                        vals['price_unit'] *= 1 + tax.amount/100
                    vals['invoice_line_tax_ids'] = tax_ids

                invoice_lines_to_create.append(vals)
        else:
            for il in invoice_lines:
                description = il['description']['selected_value']['content'] if 'description' in il else "/"
                total = il['total']['selected_value']['content'] if 'total' in il else 0.0
                subtotal = il['subtotal']['selected_value']['content'] if 'subtotal' in il else total
                unit_price = il['unit_price']['selected_value']['content'] if 'unit_price' in il else subtotal
                quantity = il['quantity']['selected_value']['content'] if 'quantity' in il else 1.0
                taxes = [value['content'] for value in il['taxes']['selected_values']] if 'taxes' in il else []
                taxes_type_ocr = [value['amount_type'] if 'amount_type' in value else 'percent' for value in il['taxes']['selected_values']] if 'taxes' in il else []

                vals = {
                    'name': description,
                    'invoice_id': self.id,
                    'price_unit': unit_price,
                    'quantity': quantity,
                }
                for (taxes, taxes_type) in pycompat.izip(taxes, taxes_type_ocr):
                    if taxes != 0.0:
                        if (taxes, taxes_type) in taxes_found:
                            if 'invoice_line_tax_ids' not in vals:
                                vals['invoice_line_tax_ids'] = [(4, taxes_found[(taxes, taxes_type)])]
                            else:
                                vals['invoice_line_tax_ids'].append((4, taxes_found[(taxes, taxes_type)]))
                        else:
                            related_documents = self.env['account.invoice'].search([('state', '!=', 'draft'), ('type', '=', self.type), ('partner_id', '=', self.partner_id.id)])
                            lines = related_documents.mapped('invoice_line_ids')
                            taxes_ids = related_documents.mapped('invoice_line_ids.invoice_line_tax_ids')
                            taxes_ids.filtered(lambda tax: tax.amount == taxes and tax.amount_type == taxes_type and tax.type_tax_use == 'purchase')
                            taxes_by_document = []
                            for tax in taxes_ids:
                                taxes_by_document.append((tax, lines.filtered(lambda line: tax in line.invoice_line_tax_ids)))
                            if len(taxes_by_document) != 0:
                                taxes_found[(taxes, taxes_type)] = max(taxes_by_document, key=lambda tax: len(tax[1]))[0].id
                                vals.setdefault('invoice_line_tax_ids', []).append((4, taxes_found[(taxes, taxes_type)]))
                            else:
                                taxes_record = self.env['account.tax'].search([('amount', '=', taxes), ('amount_type', '=', taxes_type), ('type_tax_use', '=', 'purchase'), ('company_id', '=', self.company_id.id)])
                                taxes_records_setting_based = taxes_record.filtered(lambda r: not r.price_include if line_tax_type == 'tax_excluded' else r.price_include)
                                if taxes_records_setting_based:
                                    taxes_found[(taxes, taxes_type)] = taxes_records_setting_based[0].id
                                    vals.setdefault('invoice_line_tax_ids', []).append((4, taxes_found[(taxes, taxes_type)]))
                                elif taxes_record:
                                    taxes_found[(taxes, taxes_type)] = taxes_record[0].id
                                    vals.setdefault('invoice_line_tax_ids', []).append((4, taxes_found[(taxes, taxes_type)]))
                
                if vals.get('invoice_line_tax_ids', False):
                    tax = self.env['account.tax'].browse(vals['invoice_line_tax_ids'][0][1])
                    if tax.price_include:
                        vals['price_unit'] *= 1 + tax.amount/100
                invoice_lines_to_create.append(vals)

        invoice_lines = self.invoice_line_ids.with_context(set_default_account=True, journal_id=self.journal_id.id).create(invoice_lines_to_create)

        for invoice_line in invoice_lines:
            # try to predict the account
            if getattr(invoice_line, '_predict_account', False):
                predicted_account_id = invoice_line._predict_account(invoice_line.name, invoice_line.partner_id)
                # we only change the account if we manage to predict its value
                if predicted_account_id:
                    invoice_line.account_id = predicted_account_id

        self.compute_taxes()

        total_ocr = self._context.get('total_ocr')  # this should be passed as an argument of the function but we can't change function signature in stable
        if total_ocr and len(self.tax_line_ids) > 0:
            rounding_error = self.amount_total - total_ocr
            threshold = len(invoice_lines) * self.currency_id.rounding
            if not self.currency_id.is_zero(rounding_error) and abs(rounding_error) < threshold:
                self.tax_line_ids[0].amount -= rounding_error

    @api.multi
    def _set_currency(self, currency_ocr):
        self.ensure_one()
        currency = self.env["res.currency"].search(['|', '|', ('currency_unit_label', 'ilike', currency_ocr), 
            ('name', 'ilike', currency_ocr), ('symbol', 'ilike', currency_ocr)], limit=1)
        if currency:
            self.currency_id = currency

    @api.model
    def check_all_status(self):
        for record in self.search([('state', '=', 'draft'), ('extract_state', 'in', ['waiting_extraction', 'extract_not_ready'])]):
            try:
                with self.env.cr.savepoint():
                    self._check_status(record)
                self.env.cr.commit()
            except Exception as e:
                _logger.error("Couldn't check status of account.move with id %d: %s", record.id, str(e))

    @api.multi
    def check_status(self):
        """contact iap to get the actual status of the ocr requests"""
        records_to_update = self.filtered(lambda inv: inv.extract_state in ['waiting_extraction', 'extract_not_ready'] and inv.state == 'draft')

        for record in records_to_update:
            self._check_status(record)

        limit = max(0, 20 - len(records_to_update))
        if limit > 0:
            records_to_preupdate = self.search([('extract_state', 'in', ['waiting_extraction', 'extract_not_ready']), ('id', 'not in', records_to_update.ids), ('state', '=', 'draft')], limit=limit)
            for record in records_to_preupdate:
                try:
                    with self.env.cr.savepoint():
                        self._check_status(record)
                except Exception as e:
                    _logger.error("Couldn't check status of account.move with id %d: %s", record.id, str(e))

    def _check_status(self, record):
        endpoint = self.env['ir.config_parameter'].sudo().get_param(
            'account_invoice_extract_endpoint', 'https://iap-extract.odoo.com') + '/iap/invoice_extract/get_result'
        params = {
            'version': CLIENT_OCR_VERSION,
            'document_id': record.extract_remoteid
        }
        result = jsonrpc(endpoint, params=params)
        if result['status_code'] == SUCCESS:
            record.extract_state = "waiting_validation"
            ocr_results = result['results'][0]
            record.extract_word_ids.unlink()
            self._fill_invoice_with_ocr_values(record, ocr_results)

        elif result['status_code'] == NOT_READY:
            record.extract_state = 'extract_not_ready'
        else:
            record.extract_state = 'error_status'

    @api.model
    def _fill_invoice_with_ocr_values(self, record, ocr_results):
        supplier_ocr = ocr_results['supplier']['selected_value']['content'] if 'supplier' in ocr_results else ""
        date_ocr = ocr_results['date']['selected_value']['content'] if 'date' in ocr_results else ""
        due_date_ocr = ocr_results['due_date']['selected_value']['content'] if 'due_date' in ocr_results else ""
        total_ocr = ocr_results['total']['selected_value']['content'] if 'total' in ocr_results else ""
        subtotal_ocr = ocr_results['subtotal']['selected_value']['content'] if 'subtotal' in ocr_results else ""
        invoice_id_ocr = ocr_results['invoice_id']['selected_value']['content'] if 'invoice_id' in ocr_results else ""
        currency_ocr = ocr_results['currency']['selected_value']['content'] if 'currency' in ocr_results else ""
        taxes_ocr = [value['content'] for value in ocr_results['global_taxes']['selected_values']] if 'global_taxes' in ocr_results else []
        taxes_type_ocr = [value['amount_type'] if 'amount_type' in value else 'percent' for value in ocr_results['global_taxes']['selected_values']] if 'global_taxes' in ocr_results else []
        vat_number_ocr = ocr_results['VAT_Number']['selected_value']['content'] if 'VAT_Number' in ocr_results else ""
        invoice_lines = ocr_results['invoice_lines'] if 'invoice_lines' in ocr_results else []

        if not record.invoice_line_ids:
            if invoice_lines:
                record.with_context(total_ocr=total_ocr)._set_invoice_lines(invoice_lines, subtotal_ocr)
            elif subtotal_ocr:
                vals_invoice_line = {
                    'name': "/",
                    'invoice_id': record.id,
                    'price_unit': subtotal_ocr,
                    'quantity': 1.0,
                }
                for taxes, taxes_type in pycompat.izip(taxes_ocr, taxes_type_ocr):
                    taxes_record = self.env['account.tax'].search([('amount', '=', taxes), ('amount_type', '=', taxes_type), ('type_tax_use', '=', 'purchase'), ('company_id', '=', self.company_id.id)], limit=1)
                    if taxes_record and subtotal_ocr:
                        if 'invoice_line_tax_ids' not in vals_invoice_line:
                            vals_invoice_line['invoice_line_tax_ids'] = [(4, taxes_record.id)]
                        else:
                            vals_invoice_line['invoice_line_tax_ids'].append((4, taxes_record.id))
                        vals_invoice_line['price_unit'] = subtotal_ocr
                record.invoice_line_ids.with_context(set_default_account=True, journal_id=record.journal_id.id).create(vals_invoice_line)

        record._set_supplier(supplier_ocr, vat_number_ocr)
        if not record.date_invoice:
            record.date_invoice = date_ocr
        if not record.date_due:
            record.date_due = due_date_ocr
        if not record.reference:
            record.reference = invoice_id_ocr
        if self.user_has_groups('base.group_multi_currency') and record.currency_id == self._default_currency():
            record._set_currency(currency_ocr)

        fields_with_boxes = ['supplier', 'date', 'due_date', 'invoice_id', 'currency', 'VAT_Number']
        for field in fields_with_boxes:
            if field in ocr_results:
                value = ocr_results[field]
                data = []
                for word in value["words"]:
                    data.append((0, 0, {
                        "field": field,
                        "selected_status": 1 if value["selected_value"] == word else 0,
                        "word_text": word['content'],
                        "word_page": word['page'],
                        "word_box_midX": word['coords'][0],
                        "word_box_midY": word['coords'][1],
                        "word_box_width": word['coords'][2],
                        "word_box_height": word['coords'][3],
                        "word_box_angle": word['coords'][4],
                    }))
                record.write({'extract_word_ids': data})

    @api.multi
    def buy_credits(self):
        url = self.env['iap.account'].get_credits_url(base_url='', service_name='invoice_ocr')
        return {
            'type': 'ir.actions.act_url',
            'url': url,
        }
