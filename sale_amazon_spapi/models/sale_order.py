# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from xml.etree import ElementTree

from odoo import api, models

from odoo.addons.sale_amazon_spapi import utils as amazon_utils


_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model
    def _sync_cancellations(self, account_ids=()):
        """ Synchronize the sales orders that were marked as cancelled with Amazon.

        We assume that the combined set of orders (of all accounts) to be cancelled will always be
        too small for the cron to be killed before it finishes synchronizing all order
        cancellations.

        If provided, the tuple of account ids restricts the orders waiting for synchronization to
        those whose account is listed. If it is not provided, all orders are synchronized.

        Note: This method is called by the `ir_cron_sync_amazon_cancellations` cron.

        :param tuple account_ids: The accounts whose orders should be synchronized, as a tuple of
                                  `amazon.account` record ids.
        :return: None
        """
        orders_by_account = {}

        for order in self.search(
            [('amazon_cancellation_pending', '=', True), ('order_line', '!=', False)]
        ):
            offer = order.order_line[0].amazon_offer_id
            account = offer and offer.account_id  # Offer can be deleted before the cron update
            if not account or (account_ids and account.id not in account_ids):
                continue
            orders_by_account.setdefault(account, self.env['sale.order'])
            orders_by_account[account] += order

        # Prevent redundant refresh requests.
        accounts = self.env['amazon.account'].browse(account.id for account in orders_by_account)
        amazon_utils.refresh_aws_credentials(accounts)

        for account, orders in orders_by_account.items():
            orders._cancel_on_amazon(account)

    def _cancel_on_amazon(self, account):
        """ Send a cancellation request for each of the current orders to Amazon.

        :param record account: The Amazon account of the sales order to cancel on Amazon, as an
                               `amazon.account` record.
        :return: None
        """
        def build_feed_messages(root_):
            """ Build the 'Message' elements to add to the feed.

            :param Element root_: The root XML element to which messages should be added.
            :return: None
            """
            for order_ in self:
                message_ = ElementTree.SubElement(root_, 'Message')
                order_acknowledgement_ = ElementTree.SubElement(message_, 'OrderAcknowledgement')
                ElementTree.SubElement(
                    order_acknowledgement_, 'AmazonOrderID'
                ).text = order_.amazon_order_ref
                ElementTree.SubElement(order_acknowledgement_, 'StatusCode').text = 'Failure'

        amazon_utils.ensure_account_is_set_up(account)
        xml_feed = amazon_utils.build_feed(account, 'OrderAcknowledgement', build_feed_messages)
        try:
            feed_id = amazon_utils.submit_feed(account, xml_feed, 'POST_ORDER_ACKNOWLEDGEMENT_DATA')
        except amazon_utils.AmazonRateLimitError:
            _logger.info(
                "Rate limit reached while sending order cancellations notification for Amazon "
                "account with id %s.", self.id
            )
        else:
            _logger.info(
                "Sent cancelation notification (feed id %s) to amazon for orders with "
                "amazon_order_ref %s.", feed_id, ', '.join(order.amazon_order_ref for order in self)
            )
            self.write({'amazon_cancellation_pending': False})
