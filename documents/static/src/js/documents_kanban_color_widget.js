odoo.define('documents.Many2ManyColorWidget', function (require) {
    'use strict';

    var field_registry = require('web.field_registry');

    var relational_fields = require('web.relational_fields');
    var KanbanFieldMany2ManyTags = relational_fields.KanbanFieldMany2ManyTags;

    var Many2ManyColorWidget = KanbanFieldMany2ManyTags.extend({

        /**
         * @override
         */
        start: function () {
            var self = this;
            this.trigger_up('get_search_panel_tags', {callback: function (val) {self.tags = val;}});
            return this._super.apply(this, arguments);
        },
        /**
         * @override
         * @private
         */
        _render: function () {
            var self = this;
            // In studio mode searchPanel will not be rendered and we will not have
            // tags here, in that case render standard many2many tags widget for kanban
            if (!this.tags || !this.tags.length) {
                return this._super.apply(this, arguments);
            }
            this.$el.empty().addClass('o_field_many2manytags o_kanban_tags');
            var tagIDs = _.map(this.value.data, function (m2m) {
                return m2m.data.id;
            });
            _.each(this.tags, function (tag) {
                if (tagIDs.indexOf(tag.id) > -1) {
                    var color = tag.group_hex_color || '#00000022';
                    $('<span>', {
                        class: 'o_tag',
                        text: tag.name,
                        title: tag.group_name + ' > ' + tag.name,
                    })
                    .prepend($('<span>', {
                        style: 'color: ' + color + ';',
                        text: '●',
                    }))
                    .appendTo(self.$el);
                }
            });
        },
    });

    field_registry.add('documents_kanban_color_tags', Many2ManyColorWidget);

});
