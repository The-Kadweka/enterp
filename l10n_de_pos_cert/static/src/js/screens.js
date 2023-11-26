odoo.define('l10n_de_pos_cert.screens', function (require) {
    'use strict';
    const screens = require('point_of_sale.screens');
    const core = require('web.core');
    const _t = core._t;
    const { TaxError } = require('l10n_de_pos_cert.errors');


    screens.ScreenWidget.include({
        //@Override
        _handleFailedPushForInvoice(order, refresh_screen, error){
            if (this.pos.isCountryGermanyAndFiskaly() && error.source === 'Fiskaly') {
                order = order || this.pos.get_order();
                this.invoicing = false;
                order.finalized = false;
                this.gui.show_screen('receipt', null, refresh_screen);
                this.pos._triggerFiskalyFlushErrorPopup(error);
            } else {
                this._super(order, refresh_screen, error);
            }
        }
    });

    screens.PaymentScreenWidget.include({
        async finalize_validation() {
            const _super = this._super.bind(this);
            const order = this.pos.get_order();
            // In order to not modify the base code, the second condition is needed for invoicing
            if (this.pos.isCountryGermanyAndFiskaly() && (!order.is_to_invoice() || order.get_client())) {
                order.clean_empty_paymentlines()
                if (order.isTransactionInactive()) {
                    await order.createTransaction().catch(error => {
                        if (error.status === 0) {
                            this.chrome.showFiskalyNoInternetConfirmPopup(_super);
                        } else {
                            const message = {'unknown': _t('An unknown error has occurred ! Please, contact Odoo.')};
                            this.chrome.showFiskalyErrorPopup(error, message);
                        }
                    });
                }
                if (order.isTransactionStarted()) {
                    await order.finishShortTransaction().then(() => {
                        _super();
                    }).catch(error => {
                        if (error.status === 0) {
                            this.chrome.showFiskalyNoInternetConfirmPopup(_super);
                        } else {
                            const message = {'unknown': _t('An unknown error has occurred ! Please, cancel the order by deleting it and contact Odoo.')};
                            this.chrome.showFiskalyErrorPopup(error, message);
                        }
                    });
                }
            } else {
                _super();
            }
        }
    });

    screens.ProductScreenWidget.include({
        click_product(product) {
            try {
                this._super(product);
            } catch (error) {
                if (this.pos.isCountryGermanyAndFiskaly() && error instanceof TaxError) {
                    this.chrome.showTaxError();
                } else {
                    throw error;
                }
            }
        }
    });

    screens.ScreenWidget.include({
        barcode_product_action(code) {
            try {
                this._super(code);
            } catch (error) {
                if (this.pos.isCountryGermanyAndFiskaly() && error instanceof TaxError) {
                    this.chrome.showTaxError();
                } else {
                    throw error;
                }
            }
        }
    });

    screens.ProductCategoriesWidget.include({
        perform_search(category, query, buy_result) {
            try {
                this._super(category, query, buy_result);
            } catch (error) {
                if (this.pos.isCountryGermanyAndFiskaly() && error instanceof TaxError) {
                    this.chrome.showTaxError();
                } else {
                    throw error;
                }
            }
        }
    });

    screens.ScaleScreenWidget.include({
        order_product(){
            try {
                this._super();
            } catch (error) {
                if (this.pos.isCountryGermanyAndFiskaly() && error instanceof TaxError) {
                    this.chrome.showTaxError();
                } else {
                    throw error;
                }
            }
        }
    });
});
