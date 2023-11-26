# coding: utf-8
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, models
from odoo.exceptions import UserError


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def l10n_mx_edi_request_cancellation(self):
        if self.filtered(lambda inv: inv.state not in ['draft', 'open']):
            raise UserError(_(
                'Invoice must be in draft or open state in order to be '
                'cancelled.'))
        if self.filtered('payment_move_line_ids'):
            raise UserError(_(
                'You cannot cancel an invoice which is partially paid. '
                'You need to unreconcile related payment entries first.'))
        if self.filtered(lambda inv: not inv.journal_id.update_posted):
            raise UserError(_(
                'You cannot modify a posted entry of this journal.\nFirst you '
                'should set the journal to allow cancelling entries.'))
        self.l10n_mx_edi_update_sat_status()
        invoices = self.filtered(lambda inv:
                                 inv.l10n_mx_edi_sat_status != 'cancelled')
        invoices._l10n_mx_edi_cancel()

    @api.multi
    def l10n_mx_edi_cancellation(self):
        """This method only could be called from a server action or a cron.
        Is used to cancel in Odoo al the invoices that are cancelled in the
        SAT."""
        self.l10n_mx_edi_update_sat_status()
        cancelled = self.filtered(
            lambda inv: inv.l10n_mx_edi_sat_status == 'cancelled')
        env_demo = self.mapped('company_id').filtered(
            'l10n_mx_edi_pac_test_env')
        cancelled |= self.filtered(lambda inv: inv.company_id in env_demo)
        cancelled.action_invoice_cancel()

    @api.multi
    def action_invoice_cancel(self):
        inv_mx = self.filtered(lambda r: r.l10n_mx_edi_is_required())
        if not inv_mx:
            return super(AccountInvoice, self).action_invoice_cancel()
        inv_mx.l10n_mx_edi_update_sat_status()
        to_cancel = inv_mx.filtered(
            lambda inv: inv.l10n_mx_edi_pac_status in [
                False, 'retry', 'to_sign'] or
            inv.l10n_mx_edi_sat_status == 'cancelled' or (
                inv.l10n_mx_edi_pac_status == 'cancelled' and inv.company_id.l10n_mx_edi_pac_test_env))
        is_from_cron = self._context.get('called_from_cron', False)
        if is_from_cron:
            to_cancel |= inv_mx
        for invoice in (inv_mx - to_cancel) if not is_from_cron else []:
            invoice.message_post(body=_(
                'On this invoice can not be used the cancel button, because '
                'the invoice is not cancelled in the SAT system. If you want '
                'to cancel this invoice, press the option "Request '
                'Cancellation", and when the SAT approve the cancellation '
                'this document will be cancelled automatically.'))
        return super(AccountInvoice, to_cancel).action_invoice_cancel()

    @api.model
    def l10n_mx_edi_cancellation_messages(self):
        """Method to return the cancellation messages, is called from a cron
        because the cron labels cannot be translated and that take the user
        language"""
        return {
            'to_open': _(
                'This invoice was returned to open because the CFDI is signed '
                'in the SAT system.'),
            'revert': _(
                'The reverted move in the journal entry of this invoice was '
                'cancelled because the CFDI is signed in the SAT system.'),
            'to_cancel': _(
                'This invoice already was cancelled in the SAT, now will try '
                'to cancel in Odoo.'),
        }

    @api.multi
    def l10n_mx_edi_action_open_to_cancel(self):
        """Searches all the invoices not canceled in Odoo, but marked as to
        cancel in the PAC or previously canceled in the PAC."""
        invoices = self.filtered(lambda inv: inv.l10n_mx_edi_is_required()).search([
            ('state', 'not in', ['cancel', 'paid']),
            ('payment_ids', '=', False),
            ('l10n_mx_edi_pac_status', 'in', ['to_cancel', 'cancelled']),
            ('l10n_mx_edi_sat_status', '=', 'cancelled')]).filtered(
                lambda inv: inv.l10n_mx_edi_is_required())
        message = invoices.l10n_mx_edi_cancellation_messages().get('to_cancel')
        for inv in invoices:
            inv.message_post(body=message)
        invoices.with_context(called_from_cron=True).l10n_mx_edi_cancellation()

    @api.multi
    def l10n_mx_edi_action_cancel_signed_sat(self):
        """Searches all the invoices canceled in Odoo, but valid in the SAT
        system and return to open in Odoo."""
        invoices = self.filtered(lambda inv: inv.l10n_mx_edi_is_required()).search([
            ('state', '=', 'cancel'), '|',
            ('l10n_mx_edi_pac_status', '=', 'signed'),
            ('l10n_mx_edi_sat_status', '=', 'valid')]).filtered(
                lambda inv: inv.l10n_mx_edi_is_required())
        invoices.l10n_mx_edi_update_sat_status()
        messages = invoices.l10n_mx_edi_cancellation_messages()
        for inv in invoices.filtered(lambda i: i.l10n_mx_edi_sat_status == 'valid'):
            if not inv.move_id:
                inv.write({'state': 'draft'})
                inv.action_move_create()
                inv.invoice_validate()
                inv.message_post(body=messages.get('to_open'))
                continue
            else:
                inv.move_id.reverse_entry_id.button_cancel()
                inv.message_post(body=messages.get('revert'))

    @api.multi
    def l10n_mx_edi_action_revert_cancellation(self):
        """Used when the customer do not approve the cancellation"""
        for inv in self.filtered(lambda i: i.l10n_mx_edi_is_required() and
                                 i.l10n_mx_edi_pac_status in ['to_cancel', 'cancelled']):
            inv.l10n_mx_edi_update_sat_status()
            if inv.l10n_mx_edi_sat_status == 'valid':
                inv.write({'l10n_mx_edi_pac_status': 'signed'})
