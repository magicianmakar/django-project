(function(product_id, product_suppliers, suppliers_mapping, shipping_mapping, variants_mapping) {
    'use strict';
    var product_options = {};

    var mapping_changed = false;

    function getSelectedSupplier(el) {
        return parseInt($(el).parents('tr').find('.supplier-select').val(), 10);
    }

    function getSelectedSupplierUrl(el) {
        var supplier = getSelectedSupplier(el);
        return product_suppliers[supplier].url;
    }

    function select_variant(variants, variant_title, variant_sku) {
        // variants: Shopify variants to select
        // variant_title: variant name to test if need to be selected
        // variant_sku: variant SKU to test if need to be selected

        variant_title = variant_title.toLowerCase().trim();
        if (variant_sku) {
            variant_sku = variant_sku.toLowerCase().trim();
        }

        if (typeof(variants) === 'string' && variants.toLowerCase().trim() == variant_title) {
            // Simple variant compare
            return true;
        } else {
            if (typeof(variants) === 'string') {
                if (variants.trim().startsWith('[') && variants.trim().endsWith(']')) {
                    variants = JSON.parse(variants);
                } else if (variants.indexOf(',') != -1) {
                    // variants is string list of variants separated by ,
                    variants = variants.split(',');
                }
            }

            if (typeof(variants) === 'object') {
                for (var i = 0; i < variants.length; i++) {
                    var mapped = variants[i];
                    if (typeof(mapped) === 'string') {
                        if (mapped.toLowerCase().trim() == variant_title) {
                            return true;
                        }
                    } else if (typeof(mapped) === 'object') {
                        if (mapped.sku) {
                            if (variant_sku && mapped.sku.toLowerCase().trim() == variant_sku) {
                                return true;
                            }
                        } else if (mapped.title.toLowerCase().trim() == variant_title) {
                            return true;
                        }
                    }
                }
            }
        }

        return false;
    }

    function parse_variant_map(variants) {
        if (!variants || (typeof(variants) === 'string' && !variants.trim().length)) {
            return [];
        }

        if (typeof(variants) === 'string') {
            if (variants.trim().startsWith('[') && variants.trim().endsWith(']')) {
                return JSON.parse(variants);
            } else if (variants.indexOf(',') != -1) {
                // variants is string list of variants separated by ,
                variants = variants.split(',');
                variants = variants.map(function(e) {
                    return {
                        title: e
                    };
                });

                return variants;
            } else {
                // Single variant
                return [{
                    title: variants
                }];
            }
        } else {
            return variants;
        }
    }

    // Variants Mapping
    function display_variant() {
        var option_tpl = Handlebars.compile($("#variant-option-template").html());
        $('.var-data-display').each(function(i, display) {
            $(display).empty();

            var supplier = getSelectedSupplier(display);

            var variant_data = variants_mapping[supplier][$(display).data('variant')];
            variant_data = parse_variant_map(variant_data);

            $.each(variant_data, function(j, option) {
                var optionEl = $(option_tpl({
                    option: option,
                    var_json: JSON.stringify(variant_data),
                }));

                optionEl.find('input').remove();
                optionEl.find('img').css('max-width', '25px');
                optionEl.find('.option-item-select').css('cursor', 'inherit');

                $(display).append(optionEl);
            });
        });
    }

    function selectColor() {
        $('.variants-container').find('input').each(function() {

            $(this).parents('.option-item-select').css('background-color', this.checked ? 'rgb(248, 216, 169)' : '#fff');
        });
    }

    $('.select-var-mapping').click(function(e) {
        e.preventDefault();

        $(this).bootstrapBtn('loading');

        $('#modal-variant-select').data('variant', $(this).data('variant'));
        $('#modal-variant-select').data('supplier', getSelectedSupplier(this));

        var render_options = function(response) {
            var variant_tpl = Handlebars.compile($("#variant-template").html());
            var option_tpl = Handlebars.compile($("#variant-option-template").html());
            var extra_input_tpl = Handlebars.compile($("#extra-input-template").html());

            var variant_id = $('#modal-variant-select').data('variant');
            var supplier = $('#modal-variant-select').data('supplier');

            $('.variants-container').empty();
            $.each(response, function(i, variant) {
                var variantEl = $(variant_tpl(variant));

                $.each(variant.values, function(j, option) {
                    var current_map = variants_mapping[supplier][variant_id];

                    var optionEl = $(option_tpl({
                        variant: variant,
                        option: option,
                        var_json: JSON.stringify(option),
                        selected: select_variant(current_map, option.title, option.sku)
                    }));

                    variantEl.find('.option-item, .option-item-select, .option-item-select img, .option-item-select .variant-title').click(function(e) {
                        $(this).parents('.option-item').find('input').prop('checked', true);
                        selectColor();
                    });

                    optionEl.find('input').on('change', function(e) {
                        selectColor();
                    });

                    $('.options', variantEl).append(optionEl);
                });

                $('.variants-container').append(variantEl);
            });

            // Extra varinats
            var extraEl = $(variant_tpl({
                title: 'Extra Options'
            }));
            var inputEl = $(extra_input_tpl({}));

            extraEl.find('.options').append(inputEl);

            var extra = parse_variant_map(variants_mapping[supplier][variant_id]).filter(function(e) {
                return e.extra;
            });

            var extra_values = [];
            $.each(extra, function(i, el) {
                extra_values.push(el.title);
            });

            inputEl.find('.extra-input').val(extra_values.join(','));
            inputEl.find('.extra-input').tagit({
                availableTags: '',
                autocomplete: {
                    delay: 0,
                    minLength: 0
                },
                showAutocompleteOnFocus: true,
                allowSpaces: true
            });

            $('.variants-container').append(extraEl);

            $('#modal-variant-select').modal('show');
            $('.select-var-mapping').bootstrapBtn('reset');

            selectColor();
        };

        var supplier_url = getSelectedSupplierUrl($(this));
        if (/marketplace\/product\/[0-9]+/.test(supplier_url)) {
            if (product_options[supplier_url]) {
                render_options(product_options[supplier_url]);
            } else {
                var supplier = getSelectedSupplier($(this));
                $.ajax({
                    url: '/api/marketplace-product-options',
                    type: 'POST',
                    data: {product: product_id, supplier: supplier},
                    success: function(data) {
                        product_options[supplier_url] = data;
                        render_options(data);
                    },
                    error: function(data) {
                        displayAjaxError('Variants Mapping', data);
                    }
                });
            }
        } else {
            window.extensionSendMessage({
                subject: 'getVariants',
                from: 'webapp',
                url: supplier_url,
                cache: true,
            }, render_options);
        }
    });

    $('.var-data-display, .shipping-rules-display').click(function (e) {
        e.preventDefault();

        $(this).parents('td').find('a').trigger('click');
    });


    $('#save-var-mapping').click(function(e) {
        e.preventDefault();

        var variant_id = $('#modal-variant-select').data('variant');
        var supplier = $('#modal-variant-select').data('supplier');
        var variants = [];

        $('#modal-variant-select input.variant-select').each(function() {
            if ($(this).prop('checked')) {
                variants.push(JSON.parse($(this).attr('var-data')));
            }
        });

        var extra = $('#modal-variant-select input.extra-input').val().split(',');
        $.each(extra, function(i, el) {
            if (el && el.length) {
                variants.push({
                    title: el,
                    extra: true,
                });
            }
        });

        variants_mapping[supplier][variant_id] = variants;
        $('#modal-variant-select').modal('hide');

        mapping_changed = true;

        display_variant();
    });

    // Suppliers & Shipping Mapping
    $('.change-shipping-rules').click(function(e) {
        e.preventDefault();

        var supplier = $(this).parents('tr').find('.supplier-select').val();
        var variant = $(this).parents('tr').data('variant');

        displayRulesPreview(variant);

        $('.apply-for-all').prop('checked', false);
        $('#modal-shipping-methods .modal-title').text('Shipping Methods for ' +
            product_suppliers[supplier].name + ' Supplier');

        $('#modal-shipping-methods').prop('supplier', supplier)
            .prop('variant', variant)
            .modal('show');
    });

    $('#save-shipping-rules').click(function(e) {
        var supplier = parseInt($('#modal-shipping-methods').prop('supplier'), 10);
        var variant = $('#modal-shipping-methods').prop('variant');
        var rules = getShippingRules();

        if ($('.apply-for-all').prop('checked')) {
            $.each(suppliers_mapping, function(v, el) {
                if (supplier == suppliers_mapping[v].supplier) {
                    suppliers_mapping[v].shipping = rules;
                }

                var exists = shipping_mapping.hasOwnProperty(supplier + '_' + v);
                shipping_mapping[supplier + '_' + v] = rules;
            });
        } else {
            suppliers_mapping[variant].shipping = rules;
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
            if (rule.method.length) {
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

        $.each(suppliers_mapping[variant].shipping, function(i, rule) {
            var rule_el = $(shipping_rule_tpl(rule));
            rule_el.prop('preview', true);
            rule_el.prop('rule', JSON.stringify(rule));
            $('.remove-rule', rule_el).click(function(e) {
                rule_el.remove();
            });

            container.append(rule_el);
        });
    }

    function displayRulesInTable() {
        $.each(suppliers_mapping, function(variant, info) {
            var displayEl = $('tr[data-variant="' + variant + '"] .shipping-rules-display');
            displayEl.empty();
            $.each(info.shipping, function(i, rule) {
                displayEl.append($('<span>', {
                    'class': 'badge badge-default',
                    'text': formatRulePreview(rule, info.shipping.length),
                    'title': 'Ship to <b>' + rule.country_name + '</b> using <b>' + rule.method_name + '</b>',
                    'data-container': 'body',
                    'data-html': 'true',
                }));

                if ((1 < info.shipping.length && info.shipping.length <= 3) || (i + 1) % 3 === 0) {
                    displayEl.append($('<br>'));
                }
            });
        });

        $('.shipping-rules-display .badge').bootstrapTooltip();

        display_variant();
    }

    function formatRulePreview(rule, rulesCount) {
        var price = (rule.method_name.match(/\(([^\)]+)\)/) || []).pop();
        var methods = rule.method_name.split(' ');
        var method = methods[0];

        if (rulesCount <= 3 && price) {
            return rule.country_name + ': ' + (['post', 'seller\'s', 'aliexpress'].includes(methods[1].toLowerCase()) ?
                method + ' ' + methods[1] : method) + ' ' + price;
        } else if (rulesCount <= 9) {
            return rule.country + ': ' + (['post', 'seller\'s', 'aliexpress'].includes(methods[1].toLowerCase()) ?
                method + ' ' + methods[1] : method);
        } else {
            return rule.country;
        }
    }

    function supplierSelectConfig() {
        if (document.disableSupplierSelectConfig) {
            return;
        }

        var supplier = $('.supplier-select').first().val();
        var variantsCount = $('.supplier-select').length;
        var seemVariant = $('.supplier-select').filter(function (i, el) {
            return $(el).val() == supplier;
        });

        if (seemVariant.length == variantsCount) {
            $('.supplier-config-select').val(supplier);
        } else {
            $('.supplier-config-select').val('advanced');
        }
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

    $('.supplier-select').on('change', function(e) {
        var supplier = $(this).val();
        var variant = $(this).parents('tr').data('variant');
        var mapping_key = supplier + '_' + variant;

        suppliers_mapping[variant].supplier = parseInt(supplier, 10);
        if (shipping_mapping.hasOwnProperty(mapping_key)) {
            suppliers_mapping[variant].shipping = shipping_mapping[mapping_key];
        } else {
            suppliers_mapping[variant].shipping = {};
        }

        mapping_changed = true;

        supplierSelectConfig();
        displayRulesInTable();
    });

    $('.supplier-config-select').on('change', function(e) {
        var isSupplier = $('option:selected', this).data('supplier');
        var value = $(this).val();

        document.disableSupplierSelectConfig = true;

        if (isSupplier) {
            var supplier = parseInt(value, 10);
            $('.supplier-select').filter(function(i, el) {
                return parseInt($(el).val(), 10) != supplier;
            }).val($(this).val()).trigger('change');
        } else {
            if ($(this).val()) {

            }
        }

        document.disableSupplierSelectConfig = false;
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
        $(this).bootstrapBtn('loading');

        var mapping = {
            product: product_id,
            config: $('.supplier-config-select').val(),
        };

        // This is done to save Shipping mapping when using "Apply to all variants"
        $.each(shipping_mapping, function(key, val) {
            mapping['shipping_' + key] = JSON.stringify(val);
        });

        $.each(suppliers_mapping, function(key, val) {
            mapping[key] = JSON.stringify(val);
            mapping['shipping_' + val.supplier + '_' + key] = JSON.stringify(val.shipping); // for Shipping mapping
        });

        $.each(variants_mapping, function(supplier, supplier_map) {
            $.each(supplier_map, function(variant, variant_map) {
                mapping['variant_' + supplier + '_' + variant] = JSON.stringify(variant_map);
            });
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
                this.btn.bootstrapBtn('reset');
            }
        });
    });

    //supplierSelectConfig();
    displayRulesInTable();

})(product_id, product_suppliers, suppliers_mapping, shipping_mapping, variants_mapping);