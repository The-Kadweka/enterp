odoo.define('web_mobile.datepicker', function (require) {
"use strict";

var config = require('web.config');
var mobile = require('web_mobile.rpc');
var web_datepicker = require('web.datepicker');
var Widget = require('web.Widget');

/**
 * Override odoo date-picker (bootstrap date-picker) to display mobile native
 * date picker. Because of it is better to show native mobile date-picker to
 * improve usability of Application (Due to Mobile users are used to native
 * date picker).
 */

web_datepicker.DateWidget.include({
    /**
     * @override
     */
    start: function () {
        if (!mobile.methods.requestDateTimePicker || (this.type_of_date === 'datetime' && config.device.isIOS)) {
            return this._super.apply(this, arguments);
        }
        this.$input = this.$('input.o_datepicker_input');
        // forcefully removes the library's classname to "disable" library's event listeners
        this.$input.removeClass('datetimepicker-input')
        this._setupMobilePicker();
    },

    /**
     * Bootstrap date-picker already destroyed at initialization
     *
     * @override
     */
    destroy: function () {
        if (!mobile.methods.requestDateTimePicker || (this.type_of_date === 'datetime' && config.device.isIOS)) {
            return this._super.apply(this, arguments);
        }
        Widget.prototype.destroy.apply(this, arguments);
    },

    /**
     * @override
     */
    maxDate: function () {
        if (!mobile.methods.requestDateTimePicker || (this.type_of_date === 'datetime' && config.device.isIOS)) {
            return this._super.apply(this, arguments);
        }
        console.warn('Unsupported in the mobile applications');
    },

    /**
     * @override
     */
    minDate: function () {
        if (!mobile.methods.requestDateTimePicker || (this.type_of_date === 'datetime' && config.device.isIOS)) {
            return this._super.apply(this, arguments);
        }
        console.warn('Unsupported in the mobile applications');
    },

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * @override
     * @private
     */
    _setLibInputValue: function () {
        if (!mobile.methods.requestDateTimePicker || (this.type_of_date === 'datetime' && config.device.isIOS)) {
            return this._super.apply(this, arguments);
        }
    },

    /**
     * @private
     */
    _setupMobilePicker: function () {
        var self = this;
        this.$el.on('click', function () {
            mobile.methods.requestDateTimePicker({
                'value': self.getValue() ? self.getValue().format("YYYY-MM-DD HH:mm:ss") : false,
                'type': self.type_of_date,
                'ignore_timezone': true,
            }).then(function (response) {
                self.$input.val(response.data);
                self.changeDatetime();
            });
        });
    },

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    /**
     * @override
     */
    _onInputClicked: function () {
        if (!mobile.methods.requestDateTimePicker) {
            return this._super.apply(this, arguments);
        }
    },
});

});
