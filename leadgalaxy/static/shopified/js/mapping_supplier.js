(function(product_id, product_suppliers) {
    'use strict';

    $('.select-var-mapping').click(function(e) {
        e.preventDefault();

        var supplier = $(this).parents('tr').find('.supplier-select').val();
        var variant = $(this).parents('tr').data('variant');

        displayRulesPreview(variant);

        $('.apply-for-all').prop('checked', false);
        $('#modal-shipping-methods').prop('supplier', supplier)
            .prop('variant', variant)
            .modal('show');
    });

    $('#save-shipping-rules').click(function(e) {
        var supplier = parseInt($('#modal-shipping-methods').prop('supplier'), 10);
        var variant = $('#modal-shipping-methods').prop('variant');
        var rules = getShippingRules();

        if ($('.apply-for-all').prop('checked')) {
            $.each(product_suppliers, function (v, el) {
                if (supplier == product_suppliers[v].supplier) {
                    product_suppliers[v].shipping = rules;
                }

                var exists = shipping_mapping.hasOwnProperty(supplier + '_' + v);
                shipping_mapping[supplier + '_' + v] = rules;
            });
        } else {
            product_suppliers[variant].shipping = rules;
        }

        $('#modal-shipping-methods').modal('hide');

        displayRulesInTable();
    });

    // Return current modal shipping rules
    function getShippingRules() {
        var shipping_rules = [];
        var country_index = {};

        $('#modal-shipping-methods .shipping-methods-container .shipping-rule').each(function(i, el) {
            var rule = null;

            if ($(el).prop('preview')) {
                rule = JSON.parse($(el).prop('rule'));
            } else {
                rule = {
                    country: $('.shipping-country', el).val(),
                    method: $('.shipping-method', el).val(),
                    country_name: $('.shipping-country option:selected', el).text(),
                    method_name: $('.shipping-method option:selected', el).text(),
                };
            }

            // Add rule only if a shipping method is selected
            if(rule.method.length) {
                if (country_index.hasOwnProperty(rule.country)) {
                    shipping_rules[country_index[rule.country]] = rule;
                } else {
                    country_index[rule.country] = shipping_rules.length;
                    shipping_rules.push(rule);
                }
            }
        });

        return shipping_rules;
    }

    function displayRulesPreview(variant) {
        var container = $('#modal-shipping-methods .shipping-methods-container');
        var shipping_rule_tpl = Handlebars.compile($("#shipping-rule-display-template").html());

        container.empty();

        $.each(product_suppliers[variant].shipping, function(i, rule) {
            var rule_el = $(shipping_rule_tpl(rule));
            rule_el.prop('preview', true);
            rule_el.prop('rule', JSON.stringify(rule));
            $('.remove-rule', rule_el).click(function (e) {
                rule_el.remove();
            });

            container.append(rule_el);
        });
    }

    function displayRulesInTable() {
        $.each(product_suppliers, function(variant, info) {
            var displayEl = $('tr[data-variant="' + variant + '"] .var-data-display');
            displayEl.empty();
            $.each(info.shipping, function (i, rule) {
                displayEl.append($('<span>', {
                    'class': 'badge badge-deafult m-l-xs',
                    'text': rule.country,
                    'title': 'Ship to <b>' + rule.country_name + '</b> using <b>' + rule.method_name + '</b>',
                    'style': 'cursor: help',
                    'data-container': 'body',
                    'data-html': 'true',
                }));
            });
        });

        $('.var-data-display .badge').tooltip();
    }

    function loadShippingMethods(e) {
        var select = $(e.target);

        $.ajax({
            url: '/shipping/info',
            type: 'GET',
            data: {
                'product': product_id,
                'supplier': select.parents('#modal-shipping-methods').prop('supplier'),
                'country': select.val(),
                'for': 'order',
                'type': 'json',
            },
            context: {
                select: select
            },
            success: function(data) {
                var shippingSelect = this.select.parents('.shipping-rule').find('.shipping-method');
                $.each(data.freight, function(i, el) {
                    var price = parseFloat(el.price);

                    shippingSelect.append($('<option>', {
                        text: el.companyDisplayName + ' (' + (price ? '$' + price : 'Free') + ')',
                        value: el.company,
                    }));
                });

                shippingSelect.trigger("chosen:updated");
                shippingSelect.trigger("chosen:open");
            }
        });
    }

    $('.supplier-select').on('change', function (e) {
        var supplier = $(this).val();
        var variant = $(this).parents('tr').data('variant');
        var mapping_key = supplier + '_' + variant;

        product_suppliers[variant].supplier = parseInt(supplier, 10);
        if (shipping_mapping.hasOwnProperty(mapping_key)) {
            product_suppliers[variant].shipping = shipping_mapping[mapping_key];
        } else {
            product_suppliers[variant].shipping = {};
        }

        displayRulesInTable();
    });

    $('.add-shipping-rule').click(function(e) {
        e.preventDefault();
        var shipping_rule_tpl = Handlebars.compile($("#shipping-rule-template").html());
        var rule_el = $(shipping_rule_tpl());


        $(rule_el).find('select').chosen({
            search_contains: true,
            width: '99%'
        });

        $(rule_el).find('.shipping-country').on('change', loadShippingMethods);

        $('.shipping-methods-container').append(rule_el);
    });

    $('#save-mapping').click(function(e) {
        $(this).button('loading');

        var mapping = {
            product: product_id
        };

        $.map(product_suppliers, function(val, key) {
            mapping[key] = JSON.stringify(val);
            mapping['supplier_' + val.supplier + '_' + key] = JSON.stringify(val.shipping); // for Shipping mapping
            return key;
        });

        $.ajax({
            url: '/api/suppliers-mapping',
            type: 'POST',
            data: mapping,
            context: {
                btn: $(this)
            },
            success: function(data) {
                if (data.status == 'ok') {
                    toastr.success('Suppliers Mapping', 'Mapping Saved');

                    setTimeout(function() {
                        window.location.reload();
                    }, 500);
                } else {
                    displayAjaxError('Suppliers Mapping', data);
                }
            },
            error: function(data) {
                displayAjaxError('Suppliers Mapping', data);
            },
            complete: function() {
                this.btn.button('reset');
            }
        });
    });

    displayRulesInTable();

})(product_id, product_suppliers);
