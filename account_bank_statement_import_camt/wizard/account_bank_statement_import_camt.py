# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import io
import logging
import math
import re
from functools import partial

from lxml import etree

from odoo import models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.pycompat import imap
from odoo.addons.base.models.res_bank import sanitize_account_number

_logger = logging.getLogger(__name__)

def _generic_get(*nodes, xpath, namespaces, placeholder=None):
    if placeholder is not None:
        xpath = xpath.format(placeholder=placeholder)
    for node in nodes:
        item = node.xpath(xpath, namespaces=namespaces)
        if item:
            return item[0]
    return False

# These are pair of getters: (getter for the amount, getter for the amount's currency)
_amount_getters = [
    (partial(_generic_get, xpath='ns:AmtDtls/ns:CntrValAmt/ns:Amt/text()'), partial(_generic_get, xpath='ns:AmtDtls/ns:CntrValAmt/ns:Amt/@Ccy')),
    (partial(_generic_get, xpath='ns:AmtDtls/ns:TxAmt/ns:Amt/text()'), partial(_generic_get, xpath='ns:AmtDtls/ns:TxAmt/ns:Amt/@Ccy')),
    (partial(_generic_get, xpath='ns:AmtDtls/ns:InstdAmt/ns:Amt/text()'), partial(_generic_get, xpath='ns:AmtDtls/ns:InstdAmt/ns:Amt/@Ccy')),
    (partial(_generic_get, xpath='ns:Amt/text()'), partial(_generic_get, xpath='ns:Amt/@Ccy')),
]

_charges_getters = [
    (partial(_generic_get, xpath='ns:Chrgs/ns:Rcrd/ns:Amt/text()'), partial(_generic_get, xpath='ns:Chrgs/ns:Rcrd/ns:Amt/@Ccy')),
]

_amount_charges_getters = [
    (partial(_generic_get, xpath='ns:Amt/text()'), partial(_generic_get, xpath='ns:Amt/@Ccy')),
]

# These are pair of getters: (getter for the exchange rate, getter for the target currency)
_target_rate_getters = [
    (partial(_generic_get, xpath='ns:AmtDtls/ns:CntrValAmt/ns:CcyXchg/ns:XchgRate/text()'), partial(_generic_get, xpath='ns:AmtDtls/ns:CntrValAmt/ns:CcyXchg/ns:TrgtCcy/text()')),
    (partial(_generic_get, xpath='ns:AmtDtls/ns:CntrValAmt/ns:CcyXchg/ns:XchgRate/text()'), partial(_generic_get, xpath='ns:AmtDtls/ns:CntrValAmt/ns:CcyXchg/ns:SrcCcy/text()')),
]

# These are pair of getters: (getter for the exchange rate, getter for the source currency)
_source_rate_getters = [
    (partial(_generic_get, xpath='ns:AmtDtls/ns:TxAmt/ns:CcyXchg/ns:XchgRate/text()'), partial(_generic_get, xpath='ns:AmtDtls/ns:TxAmt/ns:CcyXchg/ns:SrcCcy/text()')),
    (partial(_generic_get, xpath='ns:AmtDtls/ns:InstdAmt/ns:CcyXchg/ns:XchgRate/text()'), partial(_generic_get, xpath='ns:AmtDtls/ns:InstdAmt/ns:CcyXchg/ns:SrcCcy/text()')),
    (partial(_generic_get, xpath='ns:AmtDtls/ns:TxAmt/ns:CcyXchg/ns:XchgRate/text()'), partial(_generic_get, xpath='ns:AmtDtls/ns:TxAmt/ns:CcyXchg/ns:TrgtCcy/text()')),
    (partial(_generic_get, xpath='ns:AmtDtls/ns:InstdAmt/ns:CcyXchg/ns:XchgRate/text()'), partial(_generic_get, xpath='ns:AmtDtls/ns:InstdAmt/ns:CcyXchg/ns:TrgtCcy/text()')),
]

# These are pair of getters: (getter for the amount, getter for the amount's currency)
_currency_amount_getters = [
    (partial(_generic_get, xpath='ns:AmtDtls/ns:InstdAmt/ns:Amt/text()'), partial(_generic_get, xpath='ns:AmtDtls/ns:InstdAmt/ns:Amt/@Ccy')),
    (partial(_generic_get, xpath='ns:NtryDtls/ns:TxDtls/ns:AmtDtls/ns:InstdAmt/ns:Amt/text()'), partial(_generic_get, xpath='ns:NtryDtls/ns:TxDtls/ns:AmtDtls/ns:InstdAmt/ns:Amt/@Ccy')),
    (partial(_generic_get, xpath='ns:AmtDtls/ns:TxAmt/ns:Amt/text()'), partial(_generic_get, xpath='ns:AmtDtls/ns:TxAmt/ns:Amt/@Ccy')),
    (partial(_generic_get, xpath='ns:NtryDtls/ns:TxDtls/ns:AmtDtls/ns:TxAmt/ns:Amt/text()'), partial(_generic_get, xpath='ns:NtryDtls/ns:TxDtls/ns:AmtDtls/ns:TxAmt/ns:Amt/@Ccy')),
    (partial(_generic_get, xpath='ns:Amt/text()'), partial(_generic_get, xpath='ns:Amt/@Ccy')),
]

_get_credit_debit_indicator = partial(_generic_get,
    xpath='ns:CdtDbtInd/text()')

_get_transaction_date = partial(_generic_get,
    xpath=('ns:ValDt/ns:Dt/text()'
           '| ns:BookgDt/ns:Dt/text()'
           '| ns:BookgDt/ns:DtTm/text()'))

_get_statement_date = partial(_generic_get,
    xpath=("ns:Bal/ns:Tp/ns:CdOrPrtry[ns:Cd='CLBD']/../../ns:Dt/ns:Dt/text()"
           " | ns:Bal/ns:Tp/ns:CdOrPrtry[ns:Cd='CLBD']/../../ns:Dt/ns:DtTm/text()"
           " | ns:Bal/ns:Tp/ns:CdOrPrtry[ns:Cd='CLAV']/../../ns:Dt/ns:Dt/text()"
           " | ns:Bal/ns:Tp/ns:CdOrPrtry[ns:Cd='CLAV']/../../ns:Dt/ns:DtTm/text()"
           " | ns:Bal/ns:Tp/ns:CdOrPrtry[ns:Cd='ITBD']/../../ns:Dt/ns:Dt/text()"
           " | ns:Bal/ns:Tp/ns:CdOrPrtry[ns:Cd='ITBD']/../../ns:Dt/ns:DtTm/text()"
           ))

_get_partner_name = partial(_generic_get,
    xpath='.//ns:RltdPties/ns:{placeholder}/ns:Nm/text()')

_get_account_number = partial(_generic_get,
    xpath=('.//ns:RltdPties/ns:{placeholder}Acct/ns:Id/ns:IBAN/text()'
           '| (.//ns:{placeholder}Acct/ns:Id/ns:Othr/ns:Id)[1]/text()'))

_get_main_ref = partial(_generic_get,
    xpath='.//ns:RmtInf/ns:Strd/ns:{placeholder}RefInf/ns:Ref/text()')

_get_other_ref = partial(_generic_get,
    xpath=('ns:AcctSvcrRef/text()'
           '| {placeholder}ns:Refs/ns:TxId/text()'
           '| {placeholder}ns:Refs/ns:InstrId/text()'
           '| {placeholder}ns:Refs/ns:EndToEndId/text()'
           '| {placeholder}ns:Refs/ns:MndtId/text()'
           '| {placeholder}ns:Refs/ns:ChqNb/text()'))

def _get_signed_amount(*nodes, namespaces, journal_currency=None):
    def get_value_and_currency_name(node, getters, target_currency=None):
        for value_getter, currency_getter in getters:
            value = value_getter(node, namespaces=namespaces)
            currency_name = currency_getter(node, namespaces=namespaces)
            if value and (target_currency is None or currency_name == target_currency):
                return float(value), currency_name
        return None, None

    def get_rate(*entries, target_currency):
        for entry in entries:
            rate = get_value_and_currency_name(entry, _source_rate_getters, target_currency=target_currency)[0]
            if not rate:
                rate = get_value_and_currency_name(entry, _target_rate_getters, target_currency=target_currency)[0]
                rate = rate and 1 / rate
            if rate:
                return rate
        return None

    def get_charges(*entries, target_currency=None):
        for entry in entries:
            charges = get_value_and_currency_name(entry, _charges_getters, target_currency=target_currency)[0]
            if charges:
                return charges
        return None

    entry_details = nodes[0]
    entry = nodes[1] if len(nodes) > 1 else nodes[0]

    charges = get_charges(entry_details, entry)
    getters = _amount_charges_getters if charges else _amount_getters
 
    amount, amount_currency_name = get_value_and_currency_name(entry_details, getters)
    if not amount:
        amount, amount_currency_name = get_value_and_currency_name(entry, getters)

    if not journal_currency or amount_currency_name == journal_currency.name:
        rate = 1.0
    else:
        rate = get_rate(entry_details, entry, target_currency=journal_currency.name)
        if not rate:
            amount, amount_currency_name = get_value_and_currency_name(entry_details, _amount_getters, target_currency=journal_currency.name)
            if not amount:
                amount, amount_currency_name = get_value_and_currency_name(entry, _amount_getters, target_currency=journal_currency.name)
            if amount_currency_name == journal_currency.name:
                rate = 1.0
        if not rate:
            raise ValidationError(_("No exchange rate was found to convert an amount into the currency of the journal"))

    sign = 1 if _get_credit_debit_indicator(*nodes, namespaces=namespaces) == "CRDT" else -1
    return sign * amount * rate

def _get_counter_party(*nodes, namespaces):
    ind = _get_credit_debit_indicator(*nodes, namespaces=namespaces)
    return 'Dbtr' if ind == 'CRDT' else 'Cdtr'

# DEPRECATED (Not used anymore) -> Remove me in master
def _set_amount_currency_and_currency_id(node, path, entry_vals, currency, curr_cache, has_multi_currency, namespaces):
    instruc_amount = node.xpath('%s/text()' % path, namespaces=namespaces)
    instruc_curr = node.xpath('%s/@Ccy' % path, namespaces=namespaces)
    if (has_multi_currency and instruc_amount and instruc_curr and
            instruc_curr[0] != currency and instruc_curr[0] in curr_cache):
        entry_vals['amount_currency'] = math.copysign(abs(sum(imap(float, instruc_amount))), entry_vals['amount'])
        entry_vals['currency_id'] = curr_cache[instruc_curr[0]]

def _set_amount_in_currency(node, getters, entry_vals, currency, curr_cache, has_multi_currency, namespaces):
    for value_getter, currency_getter in getters:
        instruc_amount = value_getter(node, namespaces=namespaces)
        instruc_curr = currency_getter(node, namespaces=namespaces)
        if (has_multi_currency and instruc_amount and instruc_curr and
                instruc_curr != currency and instruc_curr in curr_cache):
            entry_vals['amount_currency'] = math.copysign(abs(float(instruc_amount)), entry_vals['amount'])
            entry_vals['currency_id'] = curr_cache[instruc_curr]
            break

def _get_transaction_name(node, namespaces):
    xpaths = ('.//ns:RmtInf/ns:Ustrd/text()',
              './/ns:RmtInf/ns:Strd/ns:CdtrRefInf/ns:Ref/text()',
               'ns:AddtlNtryInf/text()')
    for xpath in xpaths:
        transaction_name = node.xpath(xpath, namespaces=namespaces)
        if transaction_name:
            return ' '.join(transaction_name)
    return '/'

def _get_ref(node, counter_party, prefix, namespaces):
    ref = _get_main_ref(node, placeholder=counter_party, namespaces=namespaces)
    if ref is False:  # Explicitely match False, not a falsy value
        ref = _get_other_ref(node, placeholder=prefix, namespaces=namespaces)
    return ref

def _get_unique_import_id(entry, sequence, name, date, unique_import_set, namespaces):
    unique_import_ref = entry.xpath('ns:AcctSvcrRef/text()', namespaces=namespaces)
    if unique_import_ref and not _is_full_of_zeros(unique_import_ref[0]) and unique_import_ref[0] != 'NOTPROVIDED':
        entry_ref = entry.xpath('ns:NtryRef/text()', namespaces=namespaces)
        if entry_ref:
            return '{}-{}'.format(unique_import_ref[0], entry_ref[0])
        elif not entry_ref and unique_import_ref[0] not in unique_import_set:
            return unique_import_ref[0]
        else:
            return '{}-{}'.format(unique_import_ref[0], sequence)
    else:
        return '{}-{}-{}'.format(name, date, sequence)

def _is_full_of_zeros(strg):
    pattern_zero = re.compile('^0+$')
    return bool(pattern_zero.match(strg))

class AccountBankStatementImport(models.TransientModel):
    _inherit = 'account.bank.statement.import'

    def _check_camt(self, data_file):
        try:
            root = etree.parse(io.BytesIO(data_file)).getroot()
        except:
            return None
        if root.tag.find('camt.053') != -1:
            return root
        return None

    def _parse_file(self, data_file):
        root = self._check_camt(data_file)
        if root is not None:
            return self._parse_file_camt(root)
        return super(AccountBankStatementImport, self)._parse_file(data_file)

    def _parse_file_camt(self, root):
        ns = {k or 'ns': v for k, v in root.nsmap.items()}

        curr_cache = {c['name']: c['id'] for c in self.env['res.currency'].search_read([], ['id', 'name'])}
        statements_per_iban = {}
        currency_per_iban = {}
        unique_import_set = set([])
        currency = account_no = False
        has_multi_currency = self.env.user.user_has_groups('base.group_multi_currency')
        journal = self.env['account.journal'].browse(self.env.context.get('journal_id'))
        journal_currency = journal.currency_id or journal.company_id.currency_id
        for statement in root[0].findall('ns:Stmt', ns):
            statement_vals = {}
            statement_vals['name'] = statement.xpath('ns:Id/text()', namespaces=ns)[0]
            statement_vals['date'] = _get_statement_date(statement, namespaces=ns)

            # Transaction Entries 0..n
            transactions = []
            sequence = 0

            # Currency 0..1
            currency = statement.xpath('ns:Acct/ns:Ccy/text() | ns:Bal/ns:Amt/@Ccy', namespaces=ns)[0]

            if currency and journal_currency and currency != journal_currency.name:
                continue

            for entry in statement.findall('ns:Ntry', ns):
                # Date 0..1
                date = _get_transaction_date(entry, namespaces=ns) or statement_vals['date']

                transaction_details = entry.xpath('.//ns:TxDtls', namespaces=ns)
                if not transaction_details:
                    sequence += 1
                    counter_party = _get_counter_party(entry, namespaces=ns)
                    entry_vals = {
                        'sequence': sequence,
                        'date': date,
                        'amount': _get_signed_amount(entry, namespaces=ns, journal_currency=journal_currency),
                        'name': _get_transaction_name(entry, namespaces=ns),
                        'partner_name': _get_partner_name(entry, placeholder=counter_party, namespaces=ns),
                        'account_number': _get_account_number(entry, placeholder=counter_party, namespaces=ns),
                        'ref': _get_ref(entry, counter_party=counter_party, prefix='ns:NtryDtls/ns:TxDtls/', namespaces=ns),
                    }

                    entry_vals['unique_import_id'] = _get_unique_import_id(
                        entry=entry,
                        sequence=sequence,
                        name=statement_vals['name'],
                        date=entry_vals['date'],
                        unique_import_set=unique_import_set,
                        namespaces=ns)

                    _set_amount_in_currency(
                        node=entry,
                        getters=_currency_amount_getters,
                        entry_vals=entry_vals,
                        currency=currency,
                        curr_cache=curr_cache,
                        has_multi_currency=has_multi_currency,
                        namespaces=ns)

                    unique_import_set.add(entry_vals['unique_import_id'])
                    transactions.append(entry_vals)

                for entry_details in transaction_details:
                    sequence += 1
                    counter_party = _get_counter_party(entry_details, entry, namespaces=ns)
                    entry_vals = {
                        'sequence': sequence,
                        'date': date,
                        'amount': _get_signed_amount(entry_details, entry, namespaces=ns, journal_currency=journal_currency),
                        'name': _get_transaction_name(entry_details, namespaces=ns),
                        'partner_name': _get_partner_name(entry_details, placeholder=counter_party, namespaces=ns),
                        'account_number': _get_account_number(entry_details, placeholder=counter_party, namespaces=ns),
                        'ref': _get_ref(entry_details, counter_party=counter_party, prefix='', namespaces=ns),
                    }

                    entry_vals['unique_import_id'] = _get_unique_import_id(
                        entry=entry_details,
                        sequence=sequence,
                        name=statement_vals['name'],
                        date=entry_vals['date'],
                        unique_import_set=unique_import_set,
                        namespaces=ns)

                    _set_amount_in_currency(
                        node=entry_details,
                        getters=_currency_amount_getters,
                        entry_vals=entry_vals,
                        currency=currency,
                        curr_cache=curr_cache,
                        has_multi_currency=has_multi_currency,
                        namespaces=ns)

                    unique_import_set.add(entry_vals['unique_import_id'])
                    transactions.append(entry_vals)

            statement_vals['transactions'] = transactions

            # Start Balance
            # any (OPBD, PRCD, ITBD):
            #   OPBD : Opening Booked
            #   PRCD : Previous Closing Balance
            #   OPAV : Opening Available
            #   ITBD : Interim Booked (in the case of preceeding pagination)
            start_amount = float(statement.xpath(
                "ns:Bal/ns:Tp/ns:CdOrPrtry[ns:Cd='OPBD' or ns:Cd='PRCD' or ns:Cd='OPAV' or ns:Cd='ITBD']/../../ns:Amt/text()",
                namespaces=ns)[0])
            # Credit Or Debit Indicator 1..1
            sign = statement.xpath(
                "ns:Bal/ns:Tp/ns:CdOrPrtry[ns:Cd='OPBD' or ns:Cd='PRCD' or ns:Cd='OPAV' or ns:Cd='ITBD']/../../ns:CdtDbtInd/text()",
                namespaces=ns)[0]
            if sign == 'DBIT':
                start_amount *= -1
            statement_vals['balance_start'] = start_amount

            # Ending Balance
            # any (CLBD, CLAV, ITBD)
            #   CLBD : Closing Booked
            #   CLAV : Closing Available
            #   ITBD : Interim Booked
            end_amount = float(statement.xpath(
                "ns:Bal/ns:Tp/ns:CdOrPrtry[ns:Cd='CLBD' or ns:Cd='CLAV' or ns:Cd='ITBD']/../../ns:Amt/text()",
                namespaces=ns)[0])
            sign = statement.xpath(
                "ns:Bal/ns:Tp/ns:CdOrPrtry[ns:Cd='CLBD' or ns:Cd='CLAV' or ns:Cd='ITBD']/../../ns:CdtDbtInd/text()",
                namespaces=ns)[0]
            if sign == 'DBIT':
                end_amount *= -1
            statement_vals['balance_end_real'] = end_amount

            # Account Number    1..1
            # if not IBAN value then... <Othr><Id> would have.
            account_no = sanitize_account_number(statement.xpath('ns:Acct/ns:Id/ns:IBAN/text() | ns:Acct/ns:Id/ns:Othr/ns:Id/text()',
                namespaces=ns)[0])

            # Save statements and currency
            statements_per_iban.setdefault(account_no, []).append(statement_vals)
            currency_per_iban[account_no] = currency

        # If statements target multiple journals, returns thoses targeting the current journal
        if len(statements_per_iban) > 1:
            account_no = sanitize_account_number(self.env['account.journal'].browse(self.env.context.get('journal_id')).bank_acc_number)
            _logger.warning("The following statements will not be imported because they are targeting another journal (current journal id: %s):\n- %s",
                            account_no, "\n- ".join("{}: {} statement(s)".format(iban, len(statements)) for iban, statements in statements_per_iban.items() if iban != account_no))
            if not account_no:
                raise UserError(_("Please set the IBAN account on your bank journal.\n\nThis CAMT file is targeting several IBAN accounts but none match the current journal."))

        # Otherwise, returns those from only account_no
        statement_list = statements_per_iban.get(account_no, [])
        currency = currency_per_iban.get(account_no)
        return currency, account_no, statement_list
