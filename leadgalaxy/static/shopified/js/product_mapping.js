(function() {
    'use strict';

    function select_variant(variants, variant_title, variant_sku) {
        // variants: Shopify variants to select
        // variant_title: variant name to test if need to be selected
        // variant_sku: variant SKU to test if need to be selected

        variant_title = variant_title.toLowerCase().trim();
        variant_sku = variant_sku.toLowerCase().trim();

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
                            if (mapped.sku.toLowerCase().trim() == variant_sku) {
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

    $('#save-mapping').click(function(e) {
        $(this).bootstrapBtn('loading');

        $.ajax({
            url: '/api/variants-mapping',
            type: 'POST',
            data: $('#mapping-form').serialize(),
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
        $('#mapping-form').serialize();
    });

    function selectColor() {
        $('.variants-container').find('input').each(function() {

            $(this).parents('.option-item-select').css('background-color', this.checked ? 'rgb(248, 216, 169)' : '#fff');
        });
    }

    function display_variant() {
        var option_tpl = Handlebars.compile($("#variant-option-template").html());

        $('.var-data-input').each(function(i, input) {
            var display = $(input).first().next('.var-data-display');
            display.empty();

            $.each(parse_variant_map($(input).val()), function(j, option) {
                var optionEl = $(option_tpl({
                    option: option,
                    var_json: $(input).val(),
                }));

                optionEl.find('input').remove();
                optionEl.find('img').css('max-width', '25px');
                optionEl.find('.option-item-select').css('cursor', 'inherit');

                display.append(optionEl);
            });
        });
    }

    $('.select-var-mapping').click(function(e) {
        e.preventDefault();

        $(this).bootstrapBtn('loading');

        $('#modal-variant-select').data('var', $(this).data('var'));

        window.extensionSendMessage({
            subject: 'getVariants',
            from: 'webapp',
            url: $(this).attr('product-url'),
            cache: true,
        }, function(response) {
            var variant_tpl = Handlebars.compile($("#variant-template").html());
            var option_tpl = Handlebars.compile($("#variant-option-template").html());
            var extra_input_tpl = Handlebars.compile($("#extra-input-template").html());

            var variant_id = $('#modal-variant-select').data('var');
            $('.variants-container').empty();
            $.each(response, function(i, variant) {
                var variantEl = $(variant_tpl(variant));

                $.each(variant.values, function(j, option) {
                    var current_map = $('#var_' + variant_id).val();

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

            var extra = parse_variant_map($('#var_' + variant_id).val()).filter(function(e) {
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
        });
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

        $('#var_' + variant_id).val(JSON.stringify(variants));
        $('#modal-variant-select').modal('hide');

        display_variant();
    });

    display_variant();
})();