# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Mandatory fields
VAT_MANDATORY_FIELDS = [
    '012', '013', '014', '018', '021', '022', '037',
    '046', '051', '056', '065', '076', '102', '103',
    '104', '105', '152', '233', '234', '235', '236',
    '361', '362', '407', '409', '410', '419', '423',
    '436', '462', '463', '464', '765', '766', '767',
    '768',
    # Simplified-only
    '450', '801', '802',
    # Monthly-only
    '093', '097', '457',
    # 033 and 042 are mandatory when 403 is specified (always true for us, with 0% tax)
    '033', '042', '403', '414', '415', '418', '416', 
    '417', '453', '452', '451',
]

# Mapping dictionary: monthly fields as keys, list of corresponding annual fields as values
YEARLY_MONTHLY_FIELDS_TO_DELETE = [
    '472', '455', '456', '457', '458', '459', '460', '461', '454'
]

# Computation of new total fields in the annual report
YEARLY_NEW_TOTALS = {
    '080': {'add': ['077', '078', '079', '404']},
    '084': {'add': ['081', '082', '083', '405']},
    '088': {'add': ['085', '086', '087', '406']},
    '179': {'add': ['090', '092', '228']},
    '093': {'add': ['080', '084', '088', '179']},
    '101': {'add': ['098', '099', '100']},
    '102': {'add': ['093', '101'], 'subtract': ['097']},
    '104': {'add': ['102']},
    '105': {'add': ['103'], 'subtract': ['104']},
}

# Fields of the annual simplified declaration
# List drawn from : https://ecdf-developer.b2g.etat.lu/ecdf/formdocs/2020/TVA_DECAS/2020M1V002/TVA_DECAS_LINK_10_DOC_FR_2020M1V002.fieldlist
# PLUS the date fields
YEARLY_SIMPLIFIED_FIELDS = [
    '233', '234', '235', '236',
    '012', '471', '481', '450', '423', '424', '801', '802', '805', '806',
    '807', '808', '819', '820', '817', '818', '051', '056', '711', '712',
    '713', '714', '715', '716', '049', '054', '194', '065', '407', '721',
    '722', '723', '724', '725', '726', '059', '068', '195', '731', '732',
    '733', '734', '735', '736', '063', '073', '196', '409', '410', '436',
    '462', '741', '742', '743', '744', '745', '746', '431', '432', '435',
    '463', '464', '751', '752', '753', '754', '755', '756', '441', '442',
    '445', '765', '766', '761', '762', '767', '768', '763', '764', '076'
]

# New total fields in the simplified declaration
YEARLY_SIMPLIFIED_NEW_TOTALS = {
    '450': ['423', '424'],
    '481': ['472', '455', '456'],
    '076': ['802', '056', '407', '410', '768']
}
