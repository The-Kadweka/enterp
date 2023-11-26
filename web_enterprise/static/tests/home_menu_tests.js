odoo.define('web_enterprise.home_menu_tests', function (require) {
"use strict";

var HomeMenu = require('web_enterprise.HomeMenu');
var concurrency = require('web.concurrency');
var testUtils = require('web.test_utils');

QUnit.module('web_enterprise', {
    beforeEach: function () {
        this.data = {
            all_menu_ids: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            name: "root",
            children: [{
                id: 1,
                action: ' ',
                name: "Discuss",
                children: [],
             }, {
                 id: 2,
                 action: ' ',
                 name: "Calendar",
                 children: []
             }, {
                id: 3,
                action: ' ',
                name: "Contacts",
                children: [{
                    id: 4,
                    action: ' ',
                    name: "Contacts",
                    parent_id: [3, "Contacts"],
                    children: [],
                }, {
                    id: 5,
                    action: ' ',
                    name: "Configuration",
                    parent_id: [3, "Contacts"],
                    children: [{
                        id: 6,
                        action: ' ',
                        name: "Contact Tags",
                        parent_id: [5, "Configuration"],
                        children: [],
                    }, {
                        id: 7,
                        action: ' ',
                        name: "Contact Titles",
                        parent_id: [5, "Configuration"],
                        children: [],
                    }, {
                        id: 8,
                        action: ' ',
                        name: "Localization",
                        parent_id: [5, "Configuration"],
                        children: [{
                            id: 9,
                            action: ' ',
                            name: "Countries",
                            parent_id: [8, "Localization"],
                            children: [],
                        }, {
                            id: 10,
                            action: ' ',
                            name: "Fed. States",
                            parent_id: [8, "Localization"],
                            children: [],
                        }],
                    }],
                 }],
           }],
        };
    }
}, function () {

    QUnit.module('HomeMenu');

    QUnit.test('ESC Support', async function (assert) {
        assert.expect(7);

        var homeMenuHidden = false;

        var parent = testUtils.createParent({
            intercepts: {
                hide_home_menu: function () {
                    homeMenuHidden = true;
                },
            },
        });

        var homeMenu = new HomeMenu(parent, this.data);

        await homeMenu.appendTo($('#qunit-fixture'));
        homeMenu.on_attach_callback(); // simulate action manager attached to dom
        await testUtils.dom.click(homeMenu.$('input.o_menu_search_input').focus());

        // 1. search must be hidden by default
        assert.hasClass(
            homeMenu.$('div.o_menu_search'),'o_bar_hidden',
            "search must be hidden by default");

        await testUtils.fields.editInput(homeMenu.$('input.o_menu_search_input'), "dis");

        // 2. search must be visible after some input
        assert.doesNotHaveClass(homeMenu.$('div.o_menu_search'), 'o_bar_hidden',
            "search must be visible after some input");

        // 3. search must contain the input text
        assert.strictEqual(
            homeMenu.$('input.o_menu_search_input').val(),
            "dis",
            "search must contain the input text");

        var escEvent = $.Event('keydown', {
            which: $.ui.keyCode.ESCAPE,
            keyCode: $.ui.keyCode.ESCAPE,
        });

        homeMenu.$('input.o_menu_search_input').trigger(escEvent);

        // 4. search must have no text after ESC
        assert.strictEqual(
            homeMenu.$('input.o_menu_search_input').val(),
            "",
            "search must have no text after ESC");

        // 5. search must still become visible after clearing some non-empty text
        assert.doesNotHaveClass(homeMenu.$('div.o_menu_search'), 'o_bar_hidden',
            "search must still become visible after clearing some non-empty text");

        homeMenu.$('input.o_menu_search_input').trigger(escEvent);

        // 6. search must become invisible after ESC on empty text
        assert.hasClass(
            homeMenu.$('div.o_menu_search'),'o_bar_hidden',
            "search must become invisible after ESC on empty text");

        // 7. home menu must be hidden after ESC on empty text
        assert.ok(
            homeMenuHidden,
            "home menu must be hidden after ESC on empty text");

        parent.destroy();
    });

    QUnit.test('search displays matches in parents', async function (assert) {
        assert.expect(4);

        var homeMenu = new HomeMenu(parent, this.data);
        await homeMenu.appendTo($('#qunit-fixture'));
        homeMenu.on_attach_callback();

        await testUtils.dom.click(homeMenu.$('input.o_menu_search_input').focus());

        assert.containsN(homeMenu, '.o_menuitem.o_app', 3);
        assert.containsN(homeMenu, '.o_menuitem', 3);

        await testUtils.fields.editInput(homeMenu.$('input.o_menu_search_input'), "Config");

        assert.containsN(homeMenu, '.o_menuitem.o_app', 0);
        assert.containsN(homeMenu, '.o_menuitem', 6);

        homeMenu.destroy();
    });

    QUnit.test('focus stay on search input (to avoid IME disabling issue) [REQUIRE FOCUS]', async function (assert) {
        assert.expect(14);

        var parent = testUtils.createParent({});
        var homeMenu = new HomeMenu(parent, this.data);
        await homeMenu.appendTo($('#qunit-fixture'));
        homeMenu.on_attach_callback();

        // auto-focus when attached
        assert.strictEqual(document.activeElement, homeMenu.$input[0]);

        // refocus after focus on non-interactive element
        homeMenu.$('input.o_menu_search_input').blur();
        assert.strictEqual(document.activeElement, document.body);
        await testUtils.nextTick();
        assert.strictEqual(document.activeElement, homeMenu.$input[0]);

        // searching select first matching app without losing focus
        assert.containsNone(homeMenu, '.o_focused');
        await testUtils.fields.editInput(homeMenu.$input, 'a');
        assert.strictEqual(document.activeElement, homeMenu.$input[0]);
        assert.containsOnce(homeMenu, '.o_app.o_focused[data-menu="2"]');

        // switching between selected app do not lose focus
        await testUtils.fields.triggerKeydown(homeMenu.$el, 'TAB');
        assert.containsOnce(homeMenu, '.o_app.o_focused[data-menu="3"]');
        assert.strictEqual(document.activeElement, homeMenu.$input[0]);
        await testUtils.fields.triggerKeydown(homeMenu.$el, 'LEFT');
        assert.containsOnce(homeMenu, '.o_app.o_focused[data-menu="2"]');
        assert.strictEqual(document.activeElement, homeMenu.$input[0]);

        // hiding input with ESCAPE key should not lose focus
        await testUtils.fields.editInput(homeMenu.$input, '');
        assert.containsNone(homeMenu, '.o_bar_hidden');
        await testUtils.fields.triggerKeydown(homeMenu.$el, 'ESCAPE');
        assert.containsOnce(homeMenu, '.o_bar_hidden');
        assert.strictEqual(document.activeElement, homeMenu.$input[0]);

        // focusing on interactive element lose focus: this is still an issue
        // but we can't steal focus from elements such as top-left user menu
        homeMenu.$('.o_app:first').focus()
        await testUtils.nextTick();
        assert.notEqual(document.activeElement, homeMenu.$input[0]);

        parent.destroy();
    });
});
});
