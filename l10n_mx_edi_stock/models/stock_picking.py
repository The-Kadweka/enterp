# -*- coding: utf-8 -*-

import base64
import json
import pytz
import re
import requests
from lxml import etree, objectify
from werkzeug.urls import url_quote

from odoo import api, models, fields, tools, _
from odoo.exceptions import UserError

CFDI_XSLT_CADENA = 'l10n_mx_edi_stock/data/cadenaoriginal_cartaporte.xslt'
ATTACHMENT_NAME = 'CFDI_DeliveryGuide_{}.xml'
MAPBOX_GEOCODE_URL = 'https://api.mapbox.com/geocoding/v5/mapbox.places/'
MAPBOX_MATRIX_URL = 'https://api.mapbox.com/directions-matrix/v1/mapbox/driving/'

class Picking(models.Model):
    _inherit = 'stock.picking'

    country_code = fields.Char(related='company_id.country_id.code')
    l10n_mx_edi_is_export = fields.Char(compute='_l10n_mx_edi_compute_is_export')
    l10n_mx_edi_content = fields.Binary(compute='_l10n_mx_edi_compute_edi_content', compute_sudo=True)
    l10n_mx_edi_error = fields.Char(copy=False)
    l10n_mx_edi_status = fields.Selection(
        selection=[
            ('to_send', 'To Send'),
            ('sent', 'Sent'),
            ('to_cancel', 'To Cancel'),
            ('cancelled', 'Cancelled')
        ],
        string='MX EDI status',
        copy=False)
    l10n_mx_edi_sat_status = fields.Selection(
        selection=[
            ('valid', 'Valid'),
            ('cancelled', 'Cancelled'),
            ('not_found', 'Not Found'),
            ('none', 'State not defined'),
        ],
        string='SAT Status',
        copy=False)
    l10n_mx_edi_cfdi_uuid = fields.Char('Fiscal Folio', copy=False)
    l10n_mx_edi_origin = fields.Char(
        string='CFDI Origin',
        copy=False,
        help="Specify the existing Fiscal Folios to replace. Prepend with '04|'")

    l10n_mx_edi_src_lat = fields.Float(
        string='Source Latitude',
        related='picking_type_id.warehouse_id.partner_id.partner_latitude')
    l10n_mx_edi_src_lon = fields.Float(
        string='Source Longitude',
        related='picking_type_id.warehouse_id.partner_id.partner_longitude')
    l10n_mx_edi_des_lat = fields.Float(
        string='Destination Latitude',
        related='partner_id.partner_latitude')
    l10n_mx_edi_des_lon = fields.Float(
        string='Destination Longitude',
        related='partner_id.partner_longitude')
    l10n_mx_edi_distance = fields.Integer('Distance to Destination (KM)', copy=False)

    l10n_mx_edi_transport_type = fields.Selection(
        selection=[
            ('00', 'No Federal Highways'),
            ('01', 'Federal Transport'),
        ],
        string='Transport Type',
        copy=False,
        help='Specify the transportation method. The Delivery Guide will contain the Complemento Carta Porte only when'
             ' federal transport is used')
    l10n_mx_edi_vehicle_id = fields.Many2one(
        comodel_name='l10n_mx_edi.vehicle',
        string='Vehicle Setup',
        ondelete='restrict',
        copy=False,
        help='The vehicle used for Federal Transport')
    l10n_mx_edi_cfdi_file_id = fields.Many2one('ir.attachment', string='CFDI file', copy=False)
    l10n_mx_edi_cancel_picking_id = fields.Many2one(
        comodel_name='stock.picking',
        string="Substituted By",
        compute='_compute_l10n_mx_edi_cancel_picking_id',
        readonly=True)
    l10n_mx_edi_customs_no = fields.Char(
        string='Customs Number',
        help='Optional field for entering the customs information in the case '
             'of first-hand sales of imported goods or in the case of foreign trade'
             ' operations with goods or services.\n'
             'The format must be:\n'
             ' - 2 digits of the year of validation followed by two spaces.\n'
             ' - 2 digits of customs clearance followed by two spaces.\n'
             ' - 4 digits of the serial number followed by two spaces.\n'
             ' - 1 digit corresponding to the last digit of the current year, '
             'except in case of a consolidated customs initiated in the previous '
             'year of the original request for a rectification.\n'
             ' - 6 digits of the progressive numbering of the custom.\n'
             'example: 15  48  3009  0001235')

    @api.depends('partner_id')
    def _l10n_mx_edi_compute_is_export(self):
        for record in self:
            record.l10n_mx_edi_is_export = record.partner_id.country_id.code != 'MX'

    @api.depends('l10n_mx_edi_status')
    def _l10n_mx_edi_compute_edi_content(self):
        for picking in self:
            picking.l10n_mx_edi_content = base64.b64encode(picking._l10n_mx_edi_create_delivery_guide())

    def l10n_mx_edi_action_clear_error(self):
        for record in self:
            record.l10n_mx_edi_error = False

    def l10n_mx_edi_action_download(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url':  '/web/content/stock.picking/%s/l10n_mx_edi_content' % self.id
        }

    def _l10n_mx_edi_check_required_data(self):
        for record in self:
            if not record.l10n_mx_edi_transport_type:
                raise UserError(_('You must select a transport type to generate the delivery guide'))
            if record.move_line_ids.mapped('product_id').filtered(lambda product: not product.l10n_mx_edi_code_sat_id):
                raise UserError(_('All products require a SAT Code'))
            if not record.company_id.l10n_mx_edi_certificate_ids.sudo().get_valid_certificate():
                raise UserError(_('A valid certificate was not found'))
            if record.l10n_mx_edi_transport_type == '01' and not record.l10n_mx_edi_distance:
                raise UserError(_('Distance in KM must be specified when using federal transport'))

    def _compute_l10n_mx_edi_cancel_picking_id(self):
        for pick in self:
            if pick.l10n_mx_edi_cfdi_uuid:
                replaced_pick = pick.search(
                    [('l10n_mx_edi_origin', 'like', '04|%'),
                     ('l10n_mx_edi_origin', 'like', '%' + pick.l10n_mx_edi_cfdi_uuid + '%'),
                     ('company_id', '=', pick.company_id.id)],
                    limit=1,
                )
                pick.l10n_mx_edi_cancel_picking_id = replaced_pick
            else:
                pick.l10n_mx_edi_cancel_picking_id = None

    # -------------------------------------------------------------------------
    # XML
    # -------------------------------------------------------------------------
    def _l10n_mx_edi_create_delivery_guide(self):
        def format_float(val, digits=2):
            return '%.*f' % (digits, val)

        for record in self:
            name_numbers = list(re.finditer('\d+', record.name))
            mx_tz = self.env['account.move']._l10n_mx_edi_get_timezone(record.picking_type_id.warehouse_id.partner_id.state_id.code or record.company_id.partner_id.state_id.code)
            date_fmt = '%Y-%m-%dT%H:%M:%S'
            warehouse_zip = record.picking_type_id.warehouse_id.partner_id and record.picking_type_id.warehouse_id.partner_id.zip or record.company_id.zip
            origin_type, origin_uuids = None, []
            if record.l10n_mx_edi_origin and '|' in record.l10n_mx_edi_origin:
                split_origin = record.l10n_mx_edi_origin.split('|')
                if len(split_origin) == 2:
                    origin_type = split_origin[0]
                    origin_uuids = split_origin[1].split(',')
            values = {
                'cfdi_date': record.date_done.astimezone(mx_tz).strftime(date_fmt),
                'scheduled_date': record.scheduled_date.astimezone(mx_tz).strftime(date_fmt),
                'folio_number': name_numbers[-1].group(),
                'origin_type': origin_type,
                'origin_uuids': origin_uuids,
                'serie': re.sub('\W+', '', record.name[:name_numbers[-1].start()]),
                'lugar_expedicion': warehouse_zip,
                'supplier': record.company_id,
                'customer': record.partner_id.commercial_partner_id,
                'moves': record.move_lines.filtered(lambda ml: ml.quantity_done > 0),
                'record': record,
                'format_float': format_float,
                'weight_uom': self.env['product.template']._get_weight_uom_id_from_ir_config_parameter(),
            }
            xml = self.env['ir.qweb'].render(self.env.ref('l10n_mx_edi_stock.cfdi_cartaporte'), values)
            certificate = record.company_id.l10n_mx_edi_certificate_ids.sudo().get_valid_certificate()
            if certificate:
                tree = objectify.fromstring(xml)
                tree.attrib['NoCertificado'] = certificate.serial_number
                tree.attrib['Certificado'] = certificate.sudo().get_data()[0]
                cadena = record._get_cadena_chain(tree, CFDI_XSLT_CADENA)
                tree.attrib['Sello'] = certificate.sudo().get_encrypted_cadena(cadena)
                xml = etree.tostring(tree)
            return xml

    def _l10n_mx_edi_validate_with_xsd(self, xml_str, raise_error=False):
        ''' This method checks the xml_str against the combined xsd's for CartaPorte and cfd
        It is not used on every xml generated because the XSD's contain many imports which may have performance
        implications.
        :param xml_str:     The cfdi xml string.
        :param raise_error: If true, an exception is raised with the failing error message
        :return:            Boolean indicating document validity.
        '''
        combined_xsd_str = '''
        <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
            <xs:import namespace="http://www.sat.gob.mx/cfd/3" schemaLocation="http://www.sat.gob.mx/sitio_internet/cfd/3/cfdv33.xsd"/>
            <xs:import namespace="http://www.sat.gob.mx/CartaPorte20" schemaLocation="http://www.sat.gob.mx/sitio_internet/cfd/CartaPorte/CartaPorte20.xsd"/>
        </xs:schema>
        '''
        xmlschema = etree.XMLSchema(objectify.fromstring(combined_xsd_str))
        xml_doc = objectify.fromstring(xml_str)
        result = xmlschema.validate(xml_doc)
        if not result and raise_error:
            xmlschema.assertValid(xml_doc)  #if the document is invalid, raise the error for debugging
        return result

    def _get_cadena_chain(self, tree, xslt):
        xslt_root = etree.parse(tools.file_open(xslt))
        return str(etree.XSLT(xslt_root)(tree))

    def _l10n_mx_edi_decode_cfdi(self, cfdi_data=None):
        ''' Helper to extract relevant data from the CFDI to be used, for example, when printing the picking.
        :param cfdi_data:   The optional cfdi data.
        :return:            A python dictionary.
        '''
        self.ensure_one()

        def get_node(cfdi_node, attribute, namespaces):
            if hasattr(cfdi_node, 'Complemento'):
                node = cfdi_node.Complemento.xpath(attribute, namespaces=namespaces)
                return node[0] if node else None
            else:
                return None

        # Get the signed cfdi data.
        if not cfdi_data:
            cfdi_data = base64.b64decode(self.l10n_mx_edi_cfdi_file_id.datas)

        # Nothing to decode.
        if not cfdi_data:
            return {}

        cfdi_node = objectify.fromstring(cfdi_data)
        tfd_node = get_node(
            cfdi_node,
            'tfd:TimbreFiscalDigital[1]',
            {'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'},
        )

        return {
            'uuid': ({} if tfd_node is None else tfd_node).get('UUID'),
            'supplier_rfc': cfdi_node.Emisor.get('Rfc', cfdi_node.Emisor.get('rfc')),
            'customer_rfc': cfdi_node.Receptor.get('Rfc', cfdi_node.Receptor.get('rfc')),
            'amount_total': cfdi_node.get('Total', cfdi_node.get('total')),
            'cfdi_node': cfdi_node,
            'usage': cfdi_node.Receptor.get('UsoCFDI'),
            'payment_method': cfdi_node.get('formaDePago', cfdi_node.get('MetodoPago')),
            'bank_account': cfdi_node.get('NumCtaPago'),
            'sello': cfdi_node.get('sello', cfdi_node.get('Sello', 'No identificado')),
            'sello_sat': tfd_node is not None and tfd_node.get('selloSAT', tfd_node.get('SelloSAT', 'No identificado')),
            'cadena': self._get_cadena_chain(cfdi_node, CFDI_XSLT_CADENA),
            'certificate_number': cfdi_node.get('noCertificado', cfdi_node.get('NoCertificado')),
            'certificate_sat_number': tfd_node is not None and tfd_node.get('NoCertificadoSAT'),
            'expedition': cfdi_node.get('LugarExpedicion'),
            'fiscal_regime': cfdi_node.Emisor.get('RegimenFiscal', ''),
            'emission_date_str': cfdi_node.get('fecha', cfdi_node.get('Fecha', '')).replace('T', ' '),
            'stamp_date': tfd_node is not None and tfd_node.get('FechaTimbrado', '').replace('T', ' '),
        }

    # -------------------------------------------------------------------------
    # WEB SERVICES
    # -------------------------------------------------------------------------
    def _l10n_mx_edi_request_mapbox(self, url, params):
        try:
            fetched_data = requests.get(url, params=params, timeout=10)
        except Exception as e:
            raise UserError(_('Unable to connect to mapbox'))
        return fetched_data

    def l10n_mx_edi_action_set_partner_coordinates(self):
        mb_token = self.env['ir.config_parameter'].sudo().get_param('web_map.token_map_box', False)
        if not mb_token:
            raise UserError(_('Please configure MapBox to use this feature'))
        for record in self:
            src = record.picking_type_id.warehouse_id.partner_id.contact_address_complete
            dest = record.partner_id.contact_address_complete
            if not (src and dest):
                raise UserError(_('The warehouse address and the delivery address are required'))
            src_address = url_quote(src)
            url = f'{MAPBOX_GEOCODE_URL}{src_address}.json?'
            fetched_data = record._l10n_mx_edi_request_mapbox(url, {'access_token': mb_token})
            res = json.loads(fetched_data.content)
            if 'features' in res:
                record.picking_type_id.warehouse_id.partner_id.partner_latitude = res['features'][0]['geometry']['coordinates'][0]
                record.picking_type_id.warehouse_id.partner_id.partner_longitude = res['features'][0]['geometry']['coordinates'][1]
            dest_address = url_quote(dest)
            url = f'{MAPBOX_GEOCODE_URL}{dest_address}.json?'
            fetched_data = record._l10n_mx_edi_request_mapbox(url, {'access_token': mb_token})
            res = json.loads(fetched_data.content)
            if 'features' in res:
                record.partner_id.partner_latitude = res['features'][0]['geometry']['coordinates'][0]
                record.partner_id.partner_longitude = res['features'][0]['geometry']['coordinates'][1]

    def l10n_mx_edi_action_calculate_distance(self):
        mb_token = self.env['ir.config_parameter'].sudo().get_param('web_map.token_map_box', False)
        if not mb_token:
            raise UserError(_('Please configure MapBox to use this feature'))
        params = {
            'sources': 0,
            'destinations': 1,
            'annotations': 'distance',
            'access_token': mb_token,
        }
        for record in self:
            if record.l10n_mx_edi_src_lat and record.l10n_mx_edi_src_lon \
                and record.l10n_mx_edi_des_lat and record.l10n_mx_edi_des_lon:
                url = f'{MAPBOX_MATRIX_URL}{record.l10n_mx_edi_src_lat},{record.l10n_mx_edi_src_lon};{record.l10n_mx_edi_des_lat},{record.l10n_mx_edi_des_lon}'
                fetched_data = record._l10n_mx_edi_request_mapbox(url, params)
                res = json.loads(fetched_data.content)
                if 'distances' in res:
                    record.l10n_mx_edi_distance = res['distances'][0][0] // 1000
            else:
                raise UserError(_('Distance calculation requires both the source and destination coordinates'))

    def l10n_mx_edi_action_cancel_delivery_guide(self):
        for record in self:
            pac_name = record.company_id.l10n_mx_edi_pac
            credentials = getattr(self.env['account.move'], '_l10n_mx_edi_%s_info' % pac_name)(record.company_id, 'cancel')
            if credentials.get('errors'):
                record.l10n_mx_edi_error = '\n'.join(credentials['errors'])
                continue

            cancel_method = getattr(self.env['account.move'], '_l10n_mx_edi_%s_cancel_service' % pac_name)
            cancelled, code, msg = cancel_method(record.l10n_mx_edi_cfdi_uuid, record.company_id, credentials, record.l10n_mx_edi_cancel_picking_id.l10n_mx_edi_cfdi_uuid)
            if not cancelled:
                record.l10n_mx_edi_error = msg
                continue

            # == Chatter ==
            message = _("The CFDI Delivery Guide has been cancelled.")
            record._message_log(body=message)
            origin = '04|' + record.l10n_mx_edi_cfdi_uuid
            record.write({'l10n_mx_edi_cfdi_uuid': False, 'l10n_mx_edi_error': False, 'l10n_mx_edi_status': 'cancelled', 'l10n_mx_edi_origin': origin})

    def l10n_mx_edi_action_send_delivery_guide(self):
        self._l10n_mx_edi_check_required_data()
        for record in self:
            pac_name = record.company_id.l10n_mx_edi_pac

            credentials = getattr(self.env['account.move'], '_l10n_mx_edi_%s_info' % pac_name)(record.company_id, 'sign')
            if credentials.get('errors'):
                record.l10n_mx_edi_error = '\n'.join(credentials['errors'])
                continue

            cfdi_str = record._l10n_mx_edi_create_delivery_guide()
            cfdi_signed, code, msg = getattr(self.env['account.move'], '_l10n_mx_edi_%s_sign_service' % pac_name)(credentials, cfdi_str)
            if code == 'error' or not cfdi_signed:
                record.l10n_mx_edi_error = msg
                continue

            # == Create the attachment ==
            uuid = record._l10n_mx_edi_decode_cfdi(cfdi_signed).get('uuid')
            cfdi_attachment = self.env['ir.attachment'].create({
                'name': ATTACHMENT_NAME.format(uuid),
                'res_id': record.id,
                'res_model': record._name,
                'type': 'binary',
                'datas': base64.b64encode(cfdi_signed),
                'mimetype': 'application/xml',
                'description': _('Mexican Delivery Guide CFDI generated for the %s document.' % record.name),
            })
            record.l10n_mx_edi_cfdi_file_id = cfdi_attachment.id

            # == Chatter ==
            message = _("The CFDI Delivery Guide has been successfully signed.")
            record._message_log(body=message, attachment_ids=cfdi_attachment.ids)
            record.write({'l10n_mx_edi_cfdi_uuid': uuid, 'l10n_mx_edi_error': False, 'l10n_mx_edi_status': 'sent'})

    def l10n_mx_edi_action_update_sat_status(self):
        '''Synchronize both systems: Odoo & SAT to make sure the delivery guide is valid.
        '''
        for record in self:
            decoded_cfdi = record._l10n_mx_edi_decode_cfdi()
            supplier_rfc = record.company_id.vat
            customer_rfc = record.partner_id.commercial_partner_id.vat
            total = decoded_cfdi.get('amount_total', 0.0)
            uuid = decoded_cfdi.get('uuid', False)

            status = self.env['account.move']._l10n_mx_edi_get_sat_status(supplier_rfc, customer_rfc, total, uuid)
            if status.startswith('error'):
                record._message_log(body=_("Failure during update of the SAT status: %s" % status))
                continue

            record.l10n_mx_edi_sat_status = status
