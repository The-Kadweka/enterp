odoo.define('l10n_de_pos_res_cert.screens', function (require) {
    'use strict';
    const screens = require('point_of_sale.screens');
    const core = require('web.core');
    const _t = core._t;

    screens.PaymentScreenWidget.include({
        //@Override
        _handleFailedPushForInvoice(order, refresh_screen, error){
            if (this.pos.isRestaurantCountryGermanyAndFiskaly() && error.source === 'l10n_de_odoo_restaurant') {
                order = order || this.pos.get_order();
                this.invoicing = false;
                order.finalized = false;
                this.gui.show_screen('receipt', null, refresh_screen);
                this.gui.show_popup('error', {
                    'title': "No internet connection",
                    'body': "Could not sync with the Odoo server",
                });
            } else {
                this._super(order, refresh_screen, error);
            }
        },
        async finalize_validation() {
            const _super = this._super.bind(this);
            const order = this.pos.get_order();
            if (this.pos.isRestaurantCountryGermanyAndFiskaly() && (!order.is_to_invoice() || order.get_client())) {
                // In order to not modify the base code, the second condition is needed for invoicing
                try {
                    await order.retrieveAndSendLineDifference()
                } catch (e) {
                    // do nothing with the error
                }
            }
            await _super();
        }
    });
});
