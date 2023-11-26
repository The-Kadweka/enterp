# coding: utf-8
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import logging
from os.path import join, dirname, realpath
from odoo import api, SUPERUSER_ID
from odoo.tools.sql import create_column


_logger = logging.getLogger(__name__)


def uninstall_hook(cr, registry):
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'l10n_mx_edi.tariff.fraction'
    """)

def pre_init_hook(cr):
    # Skip recomputing of new fields, because it works slowly on large databases at least in Odoo v12
    create_column(cr, "product_template", "l10n_mx_edi_tariff_fraction_id", "int4")
    create_column(cr, "product_template", "l10n_mx_edi_umt_aduana_id", "int4")
    create_column(cr, "account_invoice_line", "l10n_mx_edi_tariff_fraction_id", "int4")
    create_column(cr, "account_invoice_line", "l10n_mx_edi_umt_aduana_id", "int4")

def post_init_hook(cr, registry):
    _load_locality_sat_catalog(cr, registry)
    _load_tariff_fraction_catalog(cr, registry)


def _load_locality_sat_catalog(cr, registry):
    """Import CSV data as it is faster than xml and because we can't use
    noupdate anymore with csv"""

    # Triggers temporarily added to find the ids of many2one fields
    cr.execute(
        """CREATE OR REPLACE FUNCTION l10n_mx_edi_locality()
            RETURNS trigger AS $locality$
            DECLARE
                new_array text[];
            BEGIN
                new_array := (SELECT regexp_split_to_array(NEW.name, E'--+'));
                NEW.name := new_array[1];
                NEW.state_id := (SELECT res_id FROM ir_model_data
                    WHERE name=new_array[2] and model='res.country.state');
                NEW.country_id := (SELECT res_id FROM ir_model_data
                    WHERE name='mx' and model='res.country');
                RETURN NEW;
            END;
           $locality$ LANGUAGE plpgsql;
           CREATE TRIGGER l10n_mx_edi_locality BEFORE INSERT
               ON l10n_mx_edi_res_locality
               FOR EACH ROW EXECUTE PROCEDURE l10n_mx_edi_locality();
           CREATE TRIGGER l10n_mx_edi_locality BEFORE INSERT ON res_city
               FOR EACH ROW EXECUTE PROCEDURE l10n_mx_edi_locality();
        """)

    # Read file and copy data from file
    csv_path = join(dirname(realpath(__file__)), 'data',
                    'l10n_mx_edi.res.locality.csv')
    csv_file = open(csv_path, 'rb')
    cr.copy_from(csv_file, 'l10n_mx_edi_res_locality', sep='|',
                 columns=('code', 'name'))

    csv_path = join(dirname(realpath(__file__)), 'data',
                    'res.city.csv')
    csv_file = open(csv_path, 'rb')
    cr.copy_from(
        csv_file, 'res_city', sep='|', columns=('l10n_mx_edi_code', 'name'))

    cr.execute(
        """delete from res_city where l10n_mx_edi_code is null and name in (select name from res_city where l10n_mx_edi_code is not null)""")

    # Remove triggers
    cr.execute(
        """DROP TRIGGER IF EXISTS l10n_mx_edi_locality
               ON l10n_mx_edi_res_locality;
           DROP TRIGGER IF EXISTS l10n_mx_edi_locality ON res_city;""")

    # Create xml_id, to allow make reference to this data
    # Locality
    cr.execute("""
               INSERT INTO ir_model_data (name, res_id, module, model)
               SELECT
               ('res_locality_mx_' || lower(state.code) || '_' || loc.code),
                    loc.id, 'l10n_mx_edi', 'l10n_mx_edi.res.locality'
               FROM l10n_mx_edi_res_locality AS loc, res_country_state AS state
               WHERE state.id = loc.state_id
               AND NOT EXISTS
               (SELECT * from ir_model_data
                WHERE
                module='l10n_mx_edi'
                AND name=('res_locality_mx_' || lower(state.code) || '_' || loc.code)
               )
    """)
    # City or Municipality
    cr.execute("""
               INSERT INTO ir_model_data (name, res_id, module, model)
               SELECT ('res_city_mx_' || lower(state.code)
               || '_' || city.l10n_mx_edi_code),
                city.id, 'l10n_mx_edi', 'res.city'
               FROM  res_city AS city, res_country_state AS state
               WHERE state.id = city.state_id AND city.country_id = (
                SELECT id FROM res_country WHERE code = 'MX')
               AND city.l10n_mx_edi_code IS NOT NULL
               AND NOT EXISTS
               (SELECT * from ir_model_data
                WHERE
                module='l10n_mx_edi'
                AND name=('res_city_mx_' || lower(state.code)|| '_' || city.l10n_mx_edi_code)
               )
                """)


def _load_tariff_fraction_catalog(cr, registry):
    """Import CSV data as it is faster than xml and because we can't use
    noupdate anymore with csv"""
    csv_path = join(dirname(realpath(__file__)), 'data',
                    'l10n_mx_edi.tariff.fraction.csv')
    csv_file = open(csv_path, 'rb')
    cr.copy_expert(
        """COPY l10n_mx_edi_tariff_fraction(code, name, uom_code)
           FROM STDIN WITH DELIMITER '|'""", csv_file)
    # Create xml_id, to allow make reference to this data
    cr.execute(
        """UPDATE l10n_mx_edi_tariff_fraction
        SET active = 't'""")
    cr.execute(
        """INSERT INTO ir_model_data
           (name, res_id, module, model)
           SELECT concat('tariff_fraction_', code), id,
                'l10n_mx_edi_external_trade', 'l10n_mx_edi.tariff.fraction'
           FROM l10n_mx_edi_tariff_fraction """)
