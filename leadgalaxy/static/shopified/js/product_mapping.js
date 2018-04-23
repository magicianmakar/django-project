(function(product_id, variants_mapping, shopify_options, shopify_variants) {
    'use strict';
    var product_options = {};

    var mapping_changed = false;
    var current_mappings;

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

    function getSupplierUrl() {
        var supplier = parseInt($('.supplier-select').val(), 10);
        return product_suppliers[supplier].url;
    }

    function fetchSupplierOptions(callback) {
        var supplier_url = getSupplierUrl();
        if (/marketplace\/product\/[0-9]+/.test(supplier_url)) {
            if (product_options[supplier_url]) {
                callback(product_options[supplier_url]);
            } else {
                var supplier = parseInt($('.supplier-select').val(), 10);
                $.ajax({
                    url: '/api/marketplace-product-options',
                    type: 'POST',
                    data: {
                        product: product_id,
                        supplier: supplier
                    },
                    success: function(data) {
                        product_options[supplier_url] = data;
                        callback(data);
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
            }, callback);
        }
    }

    $('#save-mapping').click(function(e) {
        $(this).bootstrapBtn('loading');

        var mapping = {
            product: product_id,
            supplier: $('.supplier-select').val(),
        };

        $.map(variants_mapping, function(val, key) {
            mapping[key] = JSON.stringify(val);
            return key;
        });

        $.ajax({
            url: '/api/variants-mapping',
            type: 'POST',
            data: mapping,
            context: {
                btn: $(this)
            },
            success: function(data) {
                if (data.status == 'ok') {
                    toastr.success('Variants Mapping', 'Mapping Saved');

                    setTimeout(function() {
                        window.location.reload();
                    }, 500);
                } else {
                    displayAjaxError('Variants Mapping', data);
                }
            },
            error: function(data) {
                displayAjaxError('Variants Mapping', data);
            },
            complete: function() {
                this.btn.bootstrapBtn('reset');
            }
        });
    });

    function selectColor() {
        $('.variants-container, .options-container').find('input').each(function() {

            $(this).parents('.option-item-select').css('background-color', this.checked ? 'rgb(248, 216, 169)' : '#fff');
        });
    }

    function display_variant() {
        var option_tpl = Handlebars.compile($("#variant-option-template").html());

        $('.var-data-display').each(function(i, display) {
            $(display).empty();

            var variant_data = variants_mapping[$(display).data('var-id')];
            variant_data = parse_variant_map(variant_data);

            $.each(variant_data, function(j, option) {
                var optionEl = $(option_tpl({
                    option: option,
                    var_json: JSON.stringify(variants_mapping[$(display).data('var-id')]),
                }));

                optionEl.find('input').remove();
                optionEl.find('img').css('max-width', '25px');
                optionEl.find('.option-item-select').css('cursor', 'inherit');

                $(display).append(optionEl);
            });
        });
    }

    $('.select-var-mapping').click(function(e) {
        e.preventDefault();

        $(this).bootstrapBtn('loading');

        $('#modal-variant-select').data('var', $(this).data('var'));

        var render_options = function(response) {
            var variant_tpl = Handlebars.compile($("#variant-template").html());
            var option_tpl = Handlebars.compile($("#variant-option-template").html());
            var extra_input_tpl = Handlebars.compile($("#extra-input-template").html());

            var variant_id = $('#modal-variant-select').data('var');
            $('.variants-container').empty();
            $.each(response, function(i, variant) {
                var variantEl = $(variant_tpl(variant));

                $.each(variant.values, function(j, option) {
                    var current_map = variants_mapping[variant_id];

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

            var extra = parse_variant_map(variants_mapping[variant_id]).filter(function(e) {
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

        fetchSupplierOptions(render_options);
    });

    $('#save-var-mapping').click(function(e) {
        e.preventDefault();

        var variant_id = $('#modal-variant-select').data('var');
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

        variants_mapping[variant_id] = variants;
        $('#modal-variant-select').modal('hide');

        mapping_changed = true;

        display_variant();
    });

    $('.supplier-select').on({
        "ready": function(e) {
            $(this).attr("readonly", true);
        },
        "focus": function(e) {
            $(this).data({
                choice: $(this).val()
            });
        },
        "change": function(e) {
            if (mapping_changed) {
                swal('Please Save your mapping changes first.');
                $(this).val($(this).data('choice'));
                return false;
            } else {
                var link = window.location.href.split(/[\?#]/)[0];
                window.location.href = link + '?supplier=' + $(this).val();

                return true;
            }
        }
    });

    $('.select-options-mapping').click(function(e) {
        e.preventDefault();

        $(this).bootstrapBtn('loading');

        var render_options = function(response) {
            var bulk_option_tpl = Handlebars.compile($("#bulk-option-template").html());
            var option_mapping_tpl = Handlebars.compile($("#option-mapping-template").html());
            var supplier_option_tpl = Handlebars.compile($("#supplier-option-template").html());
            var supplier_options = [];
            for (var i = 0; i < response.length; i++) {
                var supplier_option = {};
                supplier_option['index'] = i;
                supplier_option['title'] = response[i]['title'];
                supplier_option['values'] = [];
                for (var j = 0; j < response[i]['values'].length; j++) {
                    var option = response[i]['values'][j];
                    option['var_json'] = JSON.stringify(option);
                    supplier_option['values'].push(option);
                }
                supplier_option['shopify_options'] = shopify_options;
                supplier_options.push(supplier_option);
            }
            $('.options-container').empty();
            $.each(supplier_options, function(index, supplier_option) {
                var optionEl = $(bulk_option_tpl(supplier_option));
                optionEl.find('.shopify-option-select').change(function() {
                    var mapped = $(this).val();
                    if (mapped) {
                        mapped = parseInt(mapped);
                    } else {
                        mapped = -1;
                    }
                    var current_mapping;
                    if (current_mappings) {
                        if (current_mappings[index]['mapped'] == mapped) {
                            current_mapping = current_mappings[index];
                        }
                    }
                    if (mapped >= 0) { // The supplier option was mapped to one shopify option
                        var shopify_values = shopify_options[mapped]['values'];
                        var option_map = {
                            index: mapped,
                            supplier_values: supplier_option['values'],
                            shopify_values: shopify_values,
                        };
                        var optionMappingEl = $(option_mapping_tpl(option_map));
                        if (current_mapping) {
                            for (var i = 0; i < shopify_values.length; i++) {
                                var supplier_value = current_mapping['values'][shopify_values[i]]['title'];
                                var name = 'mapped_value_' + mapped + i;
                                optionMappingEl.find('select[name=' + name + ']').val(supplier_value);
                            }
                        }
                        optionEl.find('.options-mapping').empty().append(optionMappingEl);
                    } else { // The supplier option was mapped to "None", should select default value
                        var supplierOptionEl = $(supplier_option_tpl(supplier_option));
                        supplierOptionEl.find('.option-item, .option-item-select, .option-item-select img, .option-item-select .variant-title').click(function(e) {
                            $(this).parents('.option-item').find('input').prop('checked', true);
                            selectColor();
                        });
                        supplierOptionEl.find('input').on('change', function(e) {
                            selectColor();
                        });
                        if (current_mapping) {
                            supplierOptionEl.find('input[value="' + current_mapping['value']['title'] + '"]').prop('checked', true);
                        }
                        optionEl.find('.options-mapping').empty().append(supplierOptionEl);
                    }

                    // Disable mapped shopify options in other dropdowns
                    var values = [];
                    $('.options-container .shopify-option-select').each(function() {
                        if ($(this).val()) {
                            values.push($(this).val());
                        }
                        $(this).find('option').attr('disabled', null);
                    });
                    for (var i = 0; i < values.length; i++) {
                        $('.options-container .shopify-option-select').each(function() {
                            if (values[i] != $(this).val()) {
                                $(this).find("option[value=" + values[i] + "]").attr('disabled', 'disabled');
                            }
                        });
                    }
                });
                if (current_mappings) {
                    if (current_mappings[index] && current_mappings[index]['mapped'] >= 0) {
                        optionEl.find('.shopify-option-select').val(current_mappings[index]['mapped']);
                    }
                }
                $('.options-container').append(optionEl);
            });
            $('#mapping-error').hide();
            $('#modal-options-select').modal('show');
            $('#modal-options-select .shopify-option-select').change();
            $('.select-options-mapping').bootstrapBtn('reset');
        };

        fetchSupplierOptions(render_options);
    });

    $('#save-options-mapping').click(function(e) {
        e.preventDefault();

        var validateMapping = function(response) {
            var mappings = [];
            for (var i = 0; i < response.length; i++) {
                var mapped = $('.options-container #mapped_for_' + i).val();
                if (mapped) { // all shopify option values should be mapped to one supplier option value
                    mapped = parseInt(mapped);
                    var shopify_values = shopify_options[mapped]['values'];
                    var mapping = {
                        mapped: mapped,
                        values: {},
                    };
                    for (var j = 0; j < shopify_values.length; j++) {
                        var mapped_value = $("[name=mapped_value_" + mapped + j + "]");
                        if (mapped_value.val()) {
                            mapping['values'][shopify_values[j]] = JSON.parse(mapped_value.find('option:selected').attr('var-data'));
                        } else {
                            return false;
                        }
                    }
                    mappings.push(mapping);
                } else { // should have default value
                    var default_option = $('input[name=value_for_supplier_option_' + i + ']:checked');
                    if (default_option.length == 1) {
                        mappings.push({
                            mapped: -1,
                            value: JSON.parse(default_option.attr('var-data')),
                        });
                    } else {
                        return false;
                    }
                }
            }
            return mappings;
        };

        var saveMapping = function(response) {
            var result = validateMapping(response);
            if (result) {
                $('#mapping-error').hide();

                current_mappings = result;

                for (var variant_id in variants_mapping) {
                    if (variants_mapping.hasOwnProperty(variant_id)) {
                        variants_mapping[variant_id] = [];
                        for (var i = 0; i < current_mappings.length; i++) {
                            var mapping = current_mappings[i];
                            if (mapping['mapped'] == -1) {
                                variants_mapping[variant_id].push(mapping['value']);
                            } else {
                                var shopify_variant = shopify_variants[variant_id];
                                var shopify_value = shopify_variant['option' + (mapping['mapped'] + 1)];
                                variants_mapping[variant_id].push(mapping['values'][shopify_value]);
                            }
                        }
                    }
                }

                $('#modal-options-select').modal('hide');
                mapping_changed = true;
                display_variant();
            } else {
                $('#mapping-error').show();
            }
        };

        fetchSupplierOptions(saveMapping);
    });

    display_variant();
})(product_id, variants_mapping, shopify_options, shopify_variants);