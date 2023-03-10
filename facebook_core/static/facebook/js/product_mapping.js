/* global $, api_url, toastr, displayAjaxError, Handlebars, product_suppliers, select_variant, swal, product_id, variants_mapping */
(function(product_id, variants_mapping) {
    'use strict';
    var mapping_changed = false;

    function parse_variant_map(variants) {
        if (!variants || (typeof(variants) === 'string' && !variants.trim().length)) {
            return [];
        }

        if (typeof(variants) === 'string') {
            if (variants.trim().startsWith('[') && variants.trim().endsWith(']')) {
                return JSON.parse(variants);
            } else if (variants.indexOf(',') !== -1) {
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

    $('#save-mapping').click(function(e) {
        $(this).bootstrapBtn('loading');

        var mapping = {
            product: product_id,
            supplier: $('.supplier-select').val(),
        };

        $.map(variants_mapping, function (val, key) {
            mapping[key] = JSON.stringify(val);
            return key;
        });

        $.ajax({
            url: api_url('variants-mapping', 'fb'),
            type: 'POST',
            data: mapping,
            context: {
                btn: $(this)
            },
            success: function(data) {
                if (data.status === 'ok') {
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
        $('.variants-container').find('input').each(function() {

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

    function getSupplierUrl() {
        var supplier = parseInt($('.supplier-select').val(), 10);
        return product_suppliers[supplier].url;
    }

    function getSupplierProductId() {
        var supplier = parseInt($('.supplier-select').val(), 10);
        return product_suppliers[supplier].source_id;
    }

    $('.select-var-mapping').click(function(e) {
        e.preventDefault();

        $(this).bootstrapBtn('loading');

        $('#modal-variant-select').data('var', $(this).data('var'));

        var render_options = function(response) {
            response = response.hasOwnProperty('variant_data') ? response['variant_data'] : response;
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
                className: 'extra-mapping-options',
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

        var supplierUrl = getSupplierUrl();
        if (supplierUrl.indexOf('dropified.com') !== -1) {
            // Remove Dropified domain (matches with or without https)
            supplierUrl = supplierUrl.replace(/\S{0,}\/\/.+?\//, '/');
            $.ajax({
                url: supplierUrl,
                type: 'GET',
                data: {'variants': '1'},
                success: render_options,
                error: function(data) {
                    displayAjaxError('Variants Mapping', data);
                }
            });
        } else if (supplierUrl.indexOf('alibaba.com') !== -1){
            $.ajax({
                url: api_url('product-variants', 'alibaba'),
                type: 'GET',
                data: {'product_id': getSupplierProductId()},
                success: render_options,
                error: function(data) {
                    displayAjaxError('Alibaba Variants Mapping', data);
                }
            });
        } else {
            window.extensionSendMessage({
                subject: 'getVariants',
                from: 'webapp',
                url: supplierUrl,
                cache: true,
            }, render_options);
        }
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

    display_variant();
})(product_id, variants_mapping);
