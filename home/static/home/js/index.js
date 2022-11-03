(function(sub_conf, user_statistics) {
    'use strict';

    $('.ibox .dismiss-link').click(function() {
        var parentBox = $(this).parents('.ibox');
        var userGoalId = $(this).data('user-goal');
        parentBox.hide();
        $.ajax({
            url: '/api/goals/goal-is-viewed',
            type: 'POST',
            data: {
                user_goal_id: userGoalId
            },
        });
    });

    $('#upsell-close').on('click', function(){
        $('.upsell-backdrop, .upsell').hide();
    });

    $('.clickable').hover(function () {
        if ($(this).hasClass('clickable')) {
            $(this).removeClass('fa-circle');
            $(this).addClass('fa-check-circle');
        }
    }, function () {
        if ($(this).hasClass('clickable')) {
            $(this).removeClass('fa-check-circle');
            $(this).addClass('fa-circle');
      }
    });

    $('.goal-step').click(function () {
        var stepSlug = $(this).data('step-slug');
        var goalId = $(this).data('goal-id');
        $.ajax({
            url: '/api/goals/step-is-completed',
            type: 'POST',
            data: {
                goal_id: goalId,
                step_slug: stepSlug,
            },
            success: function(data) {
                $(this).removeClass('fa-circle clickable');
                $(this).addClass('dropified-green fa-check-circle');
                $(this).attr({'title': ""});

                var stepCircle = '.' + stepSlug + '-circle';
                $(stepCircle).removeClass('fa-circle disabled-gray');
                $(stepCircle).addClass('dropified-green fa-check-circle');

                var counter = '#total-steps-completed-' + goalId;
                $(counter).text(data.steps);
            }.bind(this),
            error: function(data) {
                displayAjaxError('Step completion', data);
            },
            complete: function () {
            }
        });
    });

    isExtensionReady().done(function () {
        $('a.extension-link').hide();
        Cookies.set('ext_installed', 'true');
        $('.goal-step[data-step-slug="install-chrome-extension"]').trigger('click');
    });

    function syncConfig() {
        window.extensionSendMessage({
            subject: 'SyncUserConfig',
            from: 'website',
            stores: true,
        }, function() {});
    }

    $("#alert_price_change").change(function() {
        var alert_price_change = $(this).val();
        $(".price-update-option").hide();
        $(".price-update-option[data-value='" + alert_price_change + "']").show();
    });
    $("#alert_price_change").change();

    $('.add-store-btn').click(function (e) {
        e.preventDefault();

        $('#modal-add-all-store-form').modal('show');
    });

    $('#select-section input[type="radio"]').on('ifChecked', function (event) {
        $('.store-box.active').removeClass('active');
        $(event.target).parent().parent().parent().parent().addClass('active');
    });

    $('#back-btn').click(function(e) {
        e.preventDefault();
        $('#wizard-nav a[href="#select-section"]').tab('show');
    });

    $('#continue-btn').click(function(e) {
        e.preventDefault();

        var storeType = $('#store-types input:checked').attr('value');

        if (storeType == 'shopify') {
            $('#add-store').show();
            $('#update-store').hide();

            $('#store-name').val('');
            $('#store-url').val('');

            $('#modal-install-form').modal('show');
        } else {
            if ($('.add-store-btn').data('extra')) {

                var extra_store_cost = $('.add-store-btn').data('store-cost');
                swal({
                    title: "Additional Store",
                    text: "You are about to add an additional store to your plan for <b>$" + extra_store_cost + "/month</b>, Would you like to continue?",
                    type: "info",
                    html: true,
                    showCancelButton: true,
                    closeOnCancel: true,
                    closeOnConfirm: true,
                    animation: false,
                    showLoaderOnConfirm: true,
                    confirmButtonText: "Yes, Add This Store",
                    cancelButtonText: "Cancel"
                }, function(isConfirmed) {
                    if (!isConfirmed) return;
                    $('#wizard-nav a[href="'+storeType+'"]').tab('show');
                });
            } else {
                $('#wizard-nav a[href="'+storeType+'"]').tab('show');
            }
        }

    });

    $('#modal-add-all-store-form').on('hidden.bs.modal', function() {
        $('#wizard-nav a[href="#select-section"]').tab('show');
    });

    $('.install-store-form').on('submit', function(e) {
        $(this).parents('.tab-pane').find('.install-store').trigger('click');

        return false;
    });

    $('.install-store').click(function (e) {
        var store_type = $(this).data('store-type');
        var shop_url = $('#' + store_type + '-shop-url').val().trim();
        var shop = null;
        var install_url = null;
        if (store_type === 'shopify') {
            shop = shop_url.match(/(?:https?:\/\/)?(?:[^:]*:[^@]*@)?([^\/\.]+)(?:\.myshopify\.com)?/);
        }
        if (store_type === 'bigcommerce') {
            shop = shop_url.match(/(?:https?:\/\/)?([^\/]+)/);
        }

        if (!shop || shop.length != 2) {
            swal('Add Store', 'Store URL is not correct!', 'error');
            return;
        } else {
            shop = shop.pop();
        }

        if (store_type === 'shopify') {
            install_url = '/shopify/install/' + shop;
        }

        if(store_type === 'bigcommerce') {
            install_url = 'https://' + shop + '/manage/marketplace/apps/' + bigcommerce_app_id;
        }

            $(this).bootstrapBtn('loading');
            window.location.href = install_url;
    });

    $('#add-store').click(function(e) {
        var url = $('#store-url').val().match(/[^\*:\/]{10,}:[^\*:]{10,}@[^\.]+\.myshopify\.com/);

        if (!url || url.length != 1) {
            swal('Add Store', 'API URL is not correct!', 'error');
            return;
        } else {
            url = 'https://' + url[0];
        }

        $('#add-store').bootstrapBtn('loading');

        $.ajax({
            url: '/api/add-store',
            type: 'POST',
            data: {
                name: $('#store-name').val(),
                url: url,
            },
            success: function(data) {
                if ('error' in data) {
                    displayAjaxError('Add Store', data);
                } else {
                    window.location.reload();
                }

            },
            error: function(data) {
                displayAjaxError('Add Store', data);
            },
            complete: function () {
                $('#add-store').bootstrapBtn('reset');
            }
        });
    });


    $('.delete-store').click(function (e) {
        var store = $(this).attr('store-id');
        var version = $(this).attr('store-version');

        swal({
            title: "Delete Store",
            text: "Are you sure that you want to delete this store?",
            type: "warning",
            showCancelButton: true,
            closeOnCancel: true,
            closeOnConfirm: false,
            animation: false,
            showLoaderOnConfirm: true,
            confirmButtonColor: "#DD6B55",
            confirmButtonText: "Delete",
            cancelButtonText: "Cancel"
        }, function(isConfirmed) {
            if (!isConfirmed) {
                return;
            }

            $.ajax({
                url: '/api/delete-store',
                type: 'POST',
                data: {
                    'store': store,
                },
                success: function(data) {
                    $('tr[store-id="'+store+'"]').remove();

                    swal.close();
                    toastr.success('Store has been deleted.', 'Delete Store');

                    syncConfig();

                    setTimeout(function() {
                        window.location.reload();
                    }, 1000);
                },
                error: function(data) {
                    displayAjaxError('Delete Store', data);
                }
            });
        });
    });

    $('form.config-form').submit(function (e) {
        e.preventDefault();

        if ($('#phone-invalid').is(':visible')) {
            toastr.error('Phone Number is not valid');
            return;
        }

        if($('.js_validate_input-message').is(':visible')){
            $('.js_validate_input-message:visible').each(function(){
                var message = $(this).attr('data-message');
                toastr.error(message);
            });
            return;
        }

        var config = $('.config-form').serialize();

        $.ajax({
            url: '/api/user-config',
            type: 'POST',
            data: config,
            context: {form: $(this)},
            success: function (data) {
                if (data.status == 'ok') {
                    toastr.success('Saved.','User Config');
                    if ($('#layout-settings').hasClass('active')) {
                        window.location.reload();
                    } else {
                        syncConfig();
                    }
                } else {
                    displayAjaxError('User Config', data);
                }
            },
            error: function (data) {
                displayAjaxError('User Config', data);
            },
            complete: function () {
            }
        });

        return false;
    });

    $('#description_mode').change(function (e) {
        if ($(this).val() == 'custom') {
            $('#desc-div').slideDown('fast');
        } else {
            $('#desc-div').slideUp('fast');
        }

        showDescriptionHelp();
    });

    function showDescriptionHelp() {
        var help = {
            empty: 'By default, no description will be used.',
            original: 'By default, the full AliExpress product description will be pre-populated.',
            simplified: 'By default, the product specs portion of the AliExpress description will be pre-populated.',
            custom: 'By default, the custom description entered below will be pre-populated.',
        };

        var val = $('#description_mode').val();
        if (val in help) {
            $('.desc-select-help').text(help[val]);
        } else {
            $('.desc-select-help').text('');
        }
    }

    $('.edit-store').click(function (e) {
        e.preventDefault();

        $('#store-name').val($(this).attr('store-name'));
        $('#store-name').attr('store-id', $(this).attr('store-id'));
        $('#store-url').val($(this).attr('store-url'));

        $('#add-store').hide();
        $('#update-store').show();

        $('#modal-add-store-form').modal('show');

    });

    $('#update-store').click(function (e) {
        e.preventDefault();

        var btn = $(this);
        var store = $('#store-name').attr('store-id');
        var name = $('#store-name').val();
        var url = $('#store-url').val().match(/[^\*:\/]{10,}:[^\*:]{10,}@[^\.]+\.myshopify\.com/);

        if (!url || url.length != 1) {
            swal('Add Store', 'API URL is not correct!', 'error');
            return;
        } else {
            url = 'https://' + url[0];
        }

        btn.bootstrapBtn('loading');

        $.ajax({
            url: '/api/update-store',
            type: 'POST',
            data: {
                store: store,
                title: name,
                url: url
            },
            context: {btn: btn},
            success: function (data) {
                if (data.status == 'ok') {
                    $('#modal-add-store-form').modal('hide');
                    toastr.success('Store information updated', 'Store update');

                    syncConfig();
                } else {
                    displayAjaxError('Store update', data);
                }
            },
            error: function (data) {
                displayAjaxError('Store update', data);
            },
            complete: function () {
                this.btn.bootstrapBtn('reset');
            }
        });
    });

    $('.show-api-url').click(function (e) {
        e.preventDefault();

        $(this).parent().find('.api-url').toggle();
    });

    $('#auto_shopify_fulfill').change(function (e) {
        var threshold = $(this).val();
        if(threshold == 'disable') {
            $('.shiping-confirmation').hide();
        } else {
            $('.shiping-confirmation').show();
        }
    });

    $('#aliexpress_fix_address').change(function (e) {
        if(!e.target.checked) {
            $('#aliexpress_fix_city').parents('.option-config-row').hide();
        } else {
            $('#aliexpress_fix_city').parents('.option-config-row').show();
        }
    });

    $('#sync_delay_notify').change(function (e) {
        if(!e.target.checked) {
            $('.sync-delay-config').hide();
        } else {
            $('.sync-delay-config').show();
        }
    });

    $('.verify-api-url').click(function (e) {
        e.preventDefault();

        $(this).bootstrapBtn('loading');

        $.ajax({
            url: '/api/store-verify',
            type: 'GET',
            data: {
                store: $(this).attr('store-id')
            },
            context: {
                btn: $(this)
            },
            success: function (data) {
                swal('API URL', 'The API URL is working properly for Shopify store:\n' + data.store, 'success');
            },
            error: function (data) {
                displayAjaxError('API URL', data);
            },
            complete: function () {
                this.btn.bootstrapBtn('reset');
            }
        });
    });

    $('.re-install-store').click(function (e) {
        e.preventDefault();

        $(this).bootstrapBtn('loading');

        var newUrl = '/shopify/install/' + $(this).attr('store-shop') + '?reinstall=' + $(this).attr('store-id');

        setTimeout(function () {
            window.location.href = newUrl;
        }, 2000);

        ga('send', 'event', {
            eventCategory: $(this).hasClass('label-danger') ?  'Store Upgrade' : 'Store Reinstall',
            eventAction: 'Shopify',
            eventLabel: $(this).attr('store-shop'),
        });
    });

    $('.change-tracking-url').click(function(e) {
        e.preventDefault();

        var storeType = $(this).attr('store-type');
        $.ajax({
            url: api_url('custom-tracking-url', storeType),
            type: 'GET',
            data: {
                store: $(this).attr('store-id'),
                storeType: storeType
            },
            success: function(data) {
                $('#custom-tracking-url-input').val(data.tracking_url);
                $('#custom-tracking-url-input').attr('store', data.store);
                $('#custom-tracking-url-input').attr('store-type', storeType);
            },
            error: function(data) {
                displayAjaxError('Custom Tracking URL', data);
            }
        });

        $("#modal-store-tracking-url").modal('show');
    });

    $('.change-currency').click(function(e) {
        e.preventDefault();

        var storeType = $(this).attr('store-type');
        $.ajax({
            url: api_url('currency', storeType),
            type: 'GET',
            data: {
                store: $(this).attr('store-id'),
                storeType: storeType
            },
            success: function(data) {
                $('#ebay_site_currency').hide();
                $('#currency-format-input label').text('Enter this store currency format:');
                $('#currency-format-input').show();
                $('#currency-input').show();
                $('#examples-currency-format-input').show();
                $('#currency-input').val(data.currency);
                $('#currency-input').attr('store', data.store);
                $('#currency-input').attr('store-type', storeType);
                if (storeType === 'ebay') {
                    $('#ebay_site_currency').show();
                    var format_currency_store = 'Store currency format: ' + data.store_currency + '{{ amount }}';
                    $('#currency-format-input label').text(format_currency_store);
                    $('#currency-input').hide();
                    $('#examples-currency-format-input').hide();
                    $('#ebay_currency').empty();
                    var currencies = data.currencies;
                    $.each(currencies, function(index, currency) {
                        $('#ebay_currency').append($('<option></option>').attr('value', currency[0]).text(currency[1]));
                        if (currency[2] === data.store_currency) {
                             $('#ebay_currency option').prop('selected', 'true');
                        }
                    });
                    $('#ebay_currency').on('change', function() {
                        var new_currency = $(this).find(':selected').text();
                        $.each(currencies, function(index, currency) {
                            if (new_currency === currency[1] && new_currency !== 'Select Currency...'){
                                format_currency_store = 'Store currency format: ' + currency[2] + '{{ amount }}';
                            } else if (new_currency === 'Select Currency...') {
                                format_currency_store = 'Store currency format: ' + data.store_currency + '{{ amount }}';
                            }
                        });
                        $('#currency-format-input label').text(format_currency_store);
                    });
                }
            },
            error: function(data) {
                displayAjaxError('Store Currency', data);
            }
        });

        $("#modal-store-currency").modal('show');
    });

    $('.change-default-location').click(function(e) {
        e.preventDefault();

        var storeId = $(this).attr('store-id');
        $('#default-location-store').val(storeId);

        $.ajax({
            url: api_url('shopify-locations'),
            type: 'GET',
            data: {
                store: storeId
            },
            success: function(data) {
                $('#default-location option').remove();
                for (var i = 0, iLength = data.locations.length; i < iLength; i++) {
                    var location = data.locations[i];
                    var option = $('<option>').val(location.id).text(location.name);
                    if (data.primary_location == location.id) {
                        option.attr('selected', true);
                    }
                    $('#default-location').append(option);
                }
            },
            error: function(data) {
                displayAjaxError('Default Location', data);
            }
        });

        $("#modal-store-default-location").modal('show');
    });

    $('#save-custom-tracking-btn').click(function (e) {
        e.preventDefault();

        var btn = $(this);
        btn.bootstrapBtn('loading');

        var tracking_url = $('#custom-tracking-url-input').val().trim();
        var store = $('#custom-tracking-url-input').attr('store');
        var storeType = $('#custom-tracking-url-input').attr('store-type');

        if (tracking_url.length && tracking_url.indexOf('{{tracking_number}}') == -1) {
            swal('Tracking URL', 'Tracking url must include {{tracking_number}}\nsee the example below custom url entry field.', 'error');
            return;
        }

        $.ajax({
            url: api_url('custom-tracking-url', storeType),
            type: 'POST',
            data: {
                store: store,
                tracking_url: tracking_url
            },
            success: function(data) {
                toastr.success('URL saved!', 'Custom Tracking URL');
                $("#modal-store-tracking-url").modal('hide');
            },
            error: function(data) {
                displayAjaxError('Custom Tracking URL', data);
            },
            complete: function () {
                btn.bootstrapBtn('reset');
            }
        });
    });

    $('#save-currency-btn').click(function (e) {
        e.preventDefault();

        var btn = $(this);
        btn.bootstrapBtn('loading');

        var currency = $('#currency-input').val().trim();
        var store = $('#currency-input').attr('store');
        var storeType = $('#currency-input').attr('store-type');
        if (storeType === 'ebay') {
            currency = $('#ebay_currency').val().trim();
        }

        $.ajax({
            url: api_url('currency', storeType),
            type: 'POST',
            data: {
                store: store,
                currency: currency
            },
            success: function(data) {
                toastr.success('Currency saved!', 'Store Currency');
                $("#modal-store-currency").modal('hide');
            },
            error: function(data) {
                displayAjaxError('Store Currency', data);
            },
            complete: function () {
                btn.bootstrapBtn('reset');
            }
        });
    });

    $('.change-tracking-domain').click(function(e) {
        e.preventDefault();

        var storeType = $(this).attr('store-type');
        $.ajax({
            url: api_url('custom-tracking-url', storeType),
            type: 'GET',
            data: {
                store: $(this).attr('store-id'),
                storeType: storeType
            },
            success: function(data) {
                var trackingInput = $('<input id="custom-tracking-domain" type="text">');
                trackingInput.val(data.tracking_url);

                // Use dropdown to show available domains
                if (data.carriers) {
                    trackingInput = $('<select id="custom-tracking-domain">');
                    trackingInput.append($('<option>'));
                    for (var i = 0, iLength = data.carriers.length; i < iLength; i++) {
                        var carrier = data.carriers[i];
                        var trackingOption = $('<option>');
                        trackingOption.val(carrier.id);
                        trackingOption.text(carrier.title);
                        if (data.tracking_url == carrier.id) {
                            trackingOption.attr('selected', true);
                        }
                        trackingInput.append(trackingOption);
                    }
                }

                trackingInput.attr('store', data.store);
                trackingInput.attr('store-type', storeType);
                trackingInput.addClass('form-control');
                $('#custom-tracking-domain-placeholder').children().remove();
                $('#custom-tracking-domain-placeholder').append(trackingInput);
            },
            error: function(data) {
                displayAjaxError('Custom Tracking URL', data);
            }
        });

        $("#modal-store-tracking-domain").modal('show');
    });

    $('#save-custom-tracking-domain-btn').click(function (e) {
        e.preventDefault();

        var btn = $(this);
        btn.bootstrapBtn('loading');

        var tracking_url = $('#custom-tracking-domain').val().trim();
        var store = $('#custom-tracking-domain').attr('store');
        var storeType = $('#custom-tracking-domain').attr('store-type');

        $.ajax({
            url: api_url('custom-tracking-url', storeType),
            type: 'POST',
            data: {
                store: store,
                tracking_url: tracking_url
            },
            success: function(data) {
                toastr.success('Carrier saved!', 'Custom Tracking Carrier');
                $("#modal-store-tracking-domain").modal('hide');
            },
            error: function(data) {
                displayAjaxError('Custom Tracking Carrier', data);
            },
            complete: function () {
                btn.bootstrapBtn('reset');
            }
        });
    });

    $('#save-default-location').click(function (e) {
        e.preventDefault();

        var btn = $(this);
        btn.bootstrapBtn('loading');

        var store = $('#default-location-store').val(),
            primaryLocation = $('#default-location').val();

        $.ajax({
            url: '/api/shopify-location',
            type: 'POST',
            data: {
                store: store,
                primary_location: primaryLocation
            },
            success: function(data) {
                toastr.success('Location Saved!', 'Default Location');
                $("#modal-store-default-location").modal('hide');
                $('.change-default-location.label-danger[store-id="' + store + '"]').addClass('hidden');
            },
            error: function(data) {
                displayAjaxError('Default Location', data);
            },
            complete: function () {
                btn.bootstrapBtn('reset');
            }
        });
    });

    $('.tracking-url-example').click(function (e) {
        e.preventDefault();

        $('#custom-tracking-url-input').val($(this).data('url'));
    });

    $('.currency-example').click(function (e) {
        e.preventDefault();

        $('#currency-input').val($(this).data('amt'));
    });

    $('input[name="order_phone_number"]').on('keyup', function() {
        var value = $(this).val();
        $('#phone-invalid').toggle(/[^\d\+-]/.test(value));
    });

    $('input[name="order_phone_number"]').trigger('keyup');

    $(document).on('keyup', '.js_validate_input', function (){
        var value = $(this).val();
        var regExp = new RegExp($(this).attr('data-regular'));
        var message = $(this).closest('div').find('.js_validate_input-message');

        message.toggle(regExp.test(value));
    });

    $('.show-clippingmagic-key-btn').click(function (e) {
        e.preventDefault();

        $(this).prev().attr('type', 'text').css('font-size', '1.0em');
        $(this).hide();
    });


    $('.edit-custom-templates-btn').click(function (e) {
        e.preventDefault();

        if (!document.editor) {
            setup_full_editor('description', false, 'editor', true);
        }

        $('#product-templates-list-modal').modal({
            backdrop: 'static',
            keyboard: false
        });
    });

    $('#product-template-modal').on('show.bs.modal', function(event) {
        $('#product-templates-list-modal').modal('hide');

        $('#add-template-form input').val('');
        $('#add-template-form textarea').val('');

        document.editor.setData('');

        var button = $(event.relatedTarget);
        if (button.hasClass('edit-template')) {
            $.ajax({
                url: '/api/description-templates',
                data: {
                    'id': button.attr('data-id')
                },
                success: function(data) {
                    var description = data.description_templates.pop();

                    $('#add-template-form input[name="id"]').val(description.id);
                    $('#add-template-form input[name="title"]').val(description.title);

                    setTimeout(function() {
                        document.editor.setData(description.description);
                    }, 100);
                },
                error: function(data) {
                    displayAjaxError('Custom Description', data);
                }
            });
        }
    });

    $('#product-template-modal').on('hide.bs.modal', function (e) {
        $('#product-templates-list-modal').modal({
            backdrop: 'static',
            keyboard: false
        });

        $('#add-template-form input').val('');
        $('#add-template-form textarea').val('');
        document.editor.setData('');
    });

    var delete_template = function(e) {
        e.preventDefault();
        var btn = $(this);

        swal({
                title: "Delete Description Template",
                text: "This will remove the description template permanently. Are you sure you want to remove it?",
                type: "warning",
                showCancelButton: true,
                closeOnConfirm: false,
                showLoaderOnConfirm: true,
                confirmButtonColor: "#DD6B55",
                confirmButtonText: "Remove Permanently",
                cancelButtonText: "Cancel"
            },
            function(isConfirmed) {
                if (isConfirmed) {
                    $.ajax({
                        type: 'DELETE',
                        url: '/api/description-templates?' + $.param({
                            id: btn.attr('data-id')
                        }),
                        success: function(data) {
                            btn.parents('.template-row').remove();

                            swal.close();
                            toastr.success("The template description has been deleted.", "Deleted!");
                        },
                        error: function(data) {
                            displayAjaxError('Delete Template Description', data);
                        }
                    });
                }
            }
        );
    };

    $('#add-template-form').on('submit', function(e) {
        e.preventDefault();

        $('#add-template-form textarea[name="description"]').val(document.editor.getData());

        $.ajax({
            url: '/api/description-templates',
            type: 'POST',
            data: $(this).serialize(),
            dataType: 'json',
            success: function (result) {
                $('#product-template-modal').modal('hide');

                var template = result.template;
                var tr = $('#description-template-table tr[data-template-id="'+template.id+'"]');
                if (tr.length === 0) {
                    tr = $('#description-template-table tbody .clone').clone();
                    tr.removeClass('hidden clone');
                    $('#description-template-table tbody').append(tr);
                }

                tr.attr('data-template-id', template.id);
                tr.find('.template-title').text(template.title);
                tr.find('.template-text').text(template.description);
                tr.find('.edit-template').attr('data-id', template.id);
                tr.find('.delete-template').attr('data-id', template.id);
                tr.find('.delete-template').attr('href', template.delete_url);
                tr.find('.delete-template').click(delete_template);
            },
            error: function (data) {
                displayAjaxError('Custom Description', data);
            }
        });

    });

    $('#description-template-table .delete-template').click(delete_template);

    $('.edit-markup-rules-btn').click(function (e) {
        e.preventDefault();

        $('#markup-rules-list-modal').modal({
            backdrop: 'static',
            keyboard: false
        });
    });

    $('#markup-rule-modal').on('show.bs.modal', function(event) {
        $('#markup-rules-list-modal').hide();

        $('#add-rule-form input').val('');

        var button = $(event.relatedTarget);
        var rule_id = button.attr('data-id');
        if (button.hasClass('edit-rule')) {
            $.ajax({
                url: '/api/markup-rules',
                data: {
                    'id': rule_id
                },
                success: function(data) {
                    for (var i = 0; i < data.markup_rules.length; i++) {
                        var markup_rule = data.markup_rules[i];
                        if (markup_rule.id.toString() == rule_id) {
                            $('#add-rule-form input[name="id"]').val(markup_rule.id);
                            $('#add-rule-form input[name="name"]').val(markup_rule.name);
                            $('#add-rule-form input[name="min_price"]').val(markup_rule.min_price);
                            $('#add-rule-form input[name="max_price"]').val(markup_rule.max_price);
                            $('#add-rule-form input[name="markup_value"]').val(markup_rule.markup_value);
                            $('#add-rule-form input[name="markup_compare_value"]').val(markup_rule.markup_compare_value);
                            $('#add-rule-form select[name="markup_type"]').val(markup_rule.markup_type);


                            $('#add-rule-form #markup_type').trigger('change');
                        }
                    }
                },
                error: function(data) {
                    displayAjaxError('Price markup rules', data);
                }
            });
        }
    });

    $('#markup-rule-modal').on('hide.bs.modal', function (e) {
        $('#markup-rules-list-modal').show();

        $('#add-rule-form input').val('');
    });


    $('#markup-rules-list-modal').on('hide.bs.modal', function (e) {
        if(window.configSyncRequired) {
            syncConfig();

            window.configSyncRequired = false;
        }
    });


    $('#add-rule-form #markup_type').on('change', function(e){

        if ($(e.currentTarget).val() == 'margin_percent') {
            $('#add-rule-form .price-markup-cont .input-group-addon').show();
        }
        else {
            $('#add-rule-form .price-markup-cont .input-group-addon').hide();
        }
    });

    var deleteMarkupRuleClicked = function(e) {
        e.preventDefault();
        var btn = $(e.currentTarget);

        swal({
                title: "Delete Price Markup Rule",
                text: "This will remove the markup rule permanently. Are you sure you want to remove it?",
                type: "warning",
                showCancelButton: true,
                closeOnConfirm: false,
                showLoaderOnConfirm: true,
                confirmButtonColor: "#DD6B55",
                confirmButtonText: "Remove Permanently",
                cancelButtonText: "Cancel"
            },
            function(isConfirmed) {
                if (isConfirmed) {
                    $.ajax({
                        type: 'DELETE',
                        url: '/api/markup-rules?' + $.param({
                            id: btn.attr('data-id')
                        }),
                        success: function(data) {
                            btn.parents('.rule-row').remove();

                            swal.close();
                            toastr.success("The markup rule has been deleted.", "Deleted!");

                            window.configSyncRequired = true;
                        },
                        error: function(data) {
                            displayAjaxError('Delete Markup Rule', data);
                        }
                    });
                }
            }
        );
    };

    $('#add-markup-rule-button').click(function(e) {
        $('#add-rule-form').trigger('submit');
    });

    $('#add-rule-form').on('submit', function(e) {
        e.preventDefault();

        $.ajax({
            url: '/api/markup-rules',
            type: 'POST',
            data: $('#add-rule-form').serialize(),
            dataType: 'json',
            success: function (result) {
                $('#markup-rule-modal').modal('hide');
                $.each(result.markup_rules, function(i, rule) {
                    var tr = $('#markup-rule-table tr[data-rule-id="'+rule.id+'"]');
                    if (tr.length === 0) {
                        tr = $('#markup-rule-table tbody .clone').clone();
                        tr.removeClass('hidden clone');
                        $('#markup-rule-table tbody').append(tr);
                    }

                    tr.attr('data-rule-id', rule.id);
                    tr.find('.rule-name').text(rule.name);
                    tr.find('.rule-min_price').text(parseFloat(rule.min_price).toFixed(2));
                    tr.find('.rule-max_price').text(rule.max_price < 0 ? '' : parseFloat(rule.max_price).toFixed(2));
                    tr.find('.rule-markup_value').text(parseFloat(rule.markup_value).toFixed(2));
                    tr.find('.rule-markup_compare_value').text(rule.markup_compare_value ? parseFloat(rule.markup_compare_value).toFixed(2) : '');
                    tr.find('.rule-markup_type').text(rule.markup_type_display);

                    tr.find('.edit-rule').attr('data-id', rule.id);
                    tr.find('.delete-rule').attr('data-id', rule.id);
                    tr.find('.delete-rule').attr('href', rule.delete_url);
                    tr.find('.delete-rule').click(deleteMarkupRuleClicked);

                    window.configSyncRequired = true;
                });
            },
            error: function (data) {
                displayAjaxError('Price markup rules', data);
            }
        });

    });


    $('#markup-rule-table .delete-rule').click(deleteMarkupRuleClicked);

    $('#chq-store-create-form').on('submit', function(e) {
        e.preventDefault();
        var url = $('#chq_store_api_url').val().match(/[^\/\.]+\.commercehq(?:dev|testing)?\.com/);

        if (!url || url.length != 1) {
            swal('Add Store', 'API URL is not correct!', 'error');
            return;
        }

        $('#chq-store-create-form [type=submit]').bootstrapBtn('loading');

        $.ajax({
            url: api_url('store-add', 'chq'),
            type: 'POST',
            data: $('#chq-store-create-form').serialize(),
            success: function(data) {
                toastr.success('Add Store', 'Your Store Have Been Added!');
                setTimeout(function() {
                    window.location.reload();
                }, 1000);
            },
            error: function(data) {
                $('#chq-store-create-form [type=submit]').bootstrapBtn('reset');
                displayAjaxError('Add Store', data);
            }
        });

        return false;
    });

    $('#chq-store-update-form').on('submit', function(e) {
        e.preventDefault();

        $('#chq-store-update-form [type=submit]').bootstrapBtn('loading');

        var upd_url = $(this).attr('action');

        var store_data = $('#chq-store-update-form').serialize();
        store_data = store_data+'&csrfmiddlewaretoken='+Cookies.get('csrftoken');

        $.ajax({
            url: upd_url,
            type: 'POST',
            data: store_data,
            success: function(data) {
                toastr.success('Edit Store', 'Your Store Have Been Updated!');
                setTimeout(function() {
                    window.location.reload();
                }, 1000);
            },
            error: function(data) {
                $('#chq-store-update-form [type=submit]').bootstrapBtn('reset');
                displayAjaxError('Edit Store', data);
            }
        });

        return false;
    });

    $('.chq-edit-store-btn').click(function(e) {
        e.preventDefault();
        var action = $(this).data('store-update-url');

        $('#chq-store-update-form').prop('action', action);

        $.get(action)
        .done(function(data) {
            $('#chq-store-update-form').html(data);
            $('#chq-store-update-modal').modal('show');
        })
        .fail(function(jqXHR) {
            if (jqXHR.status == 401) {
                window.location.reload();
            }
        });
    });

    $('.chq-delete-store-btn').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');

        swal({
            title: 'Are you sure?',
            text: 'Please, confirm if you want to delete this store.',
            type: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#DD6B55',
            confirmButtonText: 'Yes, delete it!',
            closeOnConfirm: false
        }, function() {
            $.ajax({
                url: api_url('store', 'chq') + '?' + $.param({store_id: storeId}),
                method: 'DELETE',
                success: function() {
                    $('#chq-store-row-' + storeId).hide();
                    swal('Deleted!', 'The store has been deleted.', 'success');
                }
            });
        });
    });

    $('.chq-verify-api-url').click(function (e) {
        e.preventDefault();

        $.ajax({
            url: api_url('store-verify', 'chq'),
            type: 'GET',
            data: {
                store: $(this).data('store-id')
            },
            context: {
                btn: $(this)
            },
            success: function (data) {
                swal('API URL', 'The API URL is working properly for CommerceHQ store:\n' + data.store, 'success');
            },
            error: function (data) {
                displayAjaxError('API URL', data);
            },
            complete: function () {
            }
        });
    });

    $('#gear-store-create-form').on('submit', function(e) {
        $('#gear-store-create-form [type=submit]').bootstrapBtn('loading');

        $.ajax({
            url: api_url('store-add', 'gear'),
            type: 'POST',
            data: $('#gear-store-create-form').serialize(),
            success: function(data) {
                window.location.reload(true);
            },
            error: function(data) {
                $('#gear-store-create-form [type=submit]').bootstrapBtn('reset');
                displayAjaxError('Add Store', data);
            }
        });

        return false;
    });

    $('.gear-edit-store-btn').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');
        $.get(api_url('store', 'gear'), {id: storeId}).done(function(data) {
            $('#gear-store-update-modal').modal('show');
            $('#gear-store-update-form input[name="id"]').val(data.id);
            $('#gear-store-update-form input[name="title"]').val(data.title);
            $('#gear-store-update-form input[name="api_token"]').val(data.api_token);
            $('#gear_store_mode option[value=' + data.mode + ']').prop('selected', true);
        });
    });

    $('#gear-store-update-form').on('submit', function(e) {
        $('#gear-store-update-form [type=submit]').bootstrapBtn('loading');

        $.ajax({
            url: api_url('store-update', 'gear'),
            type: 'POST',
            data: $('#gear-store-update-form').serialize(),
            success: function(data) {
                setTimeout(function() {
                    window.location.reload(true);
                }, 1000);
            },
            error: function(data) {
                $('#gear-store-update-form [type=submit]').bootstrapBtn('reset');
                displayAjaxError('Add Store', data);
            }
        });

        return false;
    });

    $('.gear-delete-store-btn').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');

        swal({
            title: 'Are you sure?',
            text: 'Please, confirm if you want to delete this store.',
            type: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#DD6B55',
            confirmButtonText: 'Yes, delete it!',
            closeOnConfirm: false
        }, function() {
            $.ajax({
                url: api_url('store', 'gear') + '?' + $.param({id: storeId}),
                method: 'DELETE',
                success: function() {
                    $('#gear-store-row-' + storeId).hide();
                    swal('Deleted!', 'The store has been deleted.', 'success');
                }
            });
        });
    });

    $('.fb-market-delete-store-btn').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');

        swal({
            title: 'Are you sure?',
            text: 'Please, confirm if you want to delete this store.',
            type: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#DD6B55',
            confirmButtonText: 'Yes, delete it!',
            closeOnConfirm: false
        }, function() {
            $.ajax({
                url: api_url('store', 'fb_marketplace') + '?' + $.param({id: storeId}),
                method: 'DELETE',
                success: function() {
                    $('#fb-marketplace-store-row-' + storeId).hide();
                    swal('Deleted!', 'The store has been deleted.', 'success');
                }
            });
        });
    });

    $('#woo-store-create-form').on('submit', function(e) {
        $('#woo-store-create-form [type=submit]').bootstrapBtn('loading');

        $.ajax({
            url: api_url('store-add', 'woo'),
            type: 'POST',
            data: $('#woo-store-create-form').serialize(),
            success: function(data) {
                window.location.replace(data.authorize_url);
            },
            error: function(data) {
                $('#woo-store-create-form [type=submit]').bootstrapBtn('reset');
                displayAjaxError('Add Store', data);
            }
        });

        return false;
    });

    $('.woo-edit-store-btn').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');
        $.get(api_url('store', 'woo'), {id: storeId}).done(function(data) {
            $('#woo-store-update-modal').modal('show');
            $('#woo-store-update-form input[name="id"]').val(data.id);
            $('#woo-store-update-form input[name="title"]').val(data.title);
            $('#woo-store-update-form input[name="api_url"]').val(data.api_url);
            $('#woo-store-update-form input[name="api_key"]').val(data.api_key);
            $('#woo-store-update-form input[name="api_password"]').val(data.api_password);
        });
    });

    $('#woo-store-update-form').on('submit', function(e) {
        $('#woo-store-update-form [type=submit]').bootstrapBtn('loading');

        $.ajax({
            url: api_url('store-update', 'woo'),
            type: 'POST',
            data: $('#woo-store-update-form').serialize(),
            success: function(data) {
                setTimeout(function() {
                    window.location.reload(true);
                }, 1000);
            },
            error: function(data) {
                $('#woo-store-update-form [type=submit]').bootstrapBtn('reset');
                displayAjaxError('Add Store', data);
            }
        });

        return false;
    });

    $('.woo-delete-store-btn').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');

        swal({
            title: 'Are you sure?',
            text: 'Please, confirm if you want to delete this store.',
            type: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#DD6B55',
            confirmButtonText: 'Yes, delete it!',
            closeOnConfirm: false
        }, function() {
            $.ajax({
                url: api_url('store', 'woo') + '?' + $.param({id: storeId}),
                method: 'DELETE',
                success: function() {
                    $('#woo-store-row-' + storeId).hide();
                    swal('Deleted!', 'The store has been deleted.', 'success');
                }
            });
        });
    });

    $('.woo-verify-api-url').click(function (e) {
        e.preventDefault();

        $.ajax({
            url: api_url('store-verify', 'woo'),
            type: 'GET',
            data: {
                store: $(this).data('store-id')
            },
            context: {
                btn: $(this)
            },
            success: function (data) {
                swal('API URL', 'The API URL is working properly for WooCommerce store:\n' + data.store, 'success');
            },
            error: function (data) {
                displayAjaxError('API URL', data);
            },
            complete: function () {
            }
        });
    });

    $('#gk-store-create-form').on('submit', function(e) {
        var form = $(this);
        form.find('[type=submit]').bootstrapBtn('loading');

        $.ajax({
            url: api_url('store-add', 'gkart'),
            type: 'POST',
            data: $(this).serialize(),
            context: {form: form},
            success: function(data) {
                window.location.reload(true);
            },
            error: function(data) {
                form.find('[type=submit]').bootstrapBtn('reset');
                displayAjaxError('Add Store', data);
            }
        });

        return false;
    });

    $('#gk-lite-store-create-form').on('submit', function(e) {
        var form = $(this);
        form.find('[type=submit]').bootstrapBtn('loading');

        var checkoutPage = window.open('about:blank');
        $.ajax({
            url: api_url('store-add', 'gkart'),
            type: 'POST',
            data: $(this).serialize(),
            context: {form: form},
            success: function(data) {
                checkoutPage.location.href = 'https://groovekart.groovesell.com/dropified/' + data.t;
                form.find('[type=submit]').bootstrapBtn('reset');
                $('#modal-add-all-store-form').modal('hide');
            },
            error: function(data) {
                checkoutPage.close();
                form.find('[type=submit]').bootstrapBtn('reset');
                displayAjaxError('Add Store', data);
            }
        });

        return false;
    });

    $('.gk-edit-store-btn').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');
        $.get(api_url('store', 'gkart'), {id: storeId}).done(function(data) {
            $('#gk-store-update-modal').modal('show');
            $('#gk-store-update-form input[name="id"]').val(data.id);
            $('#gk-store-update-form input[name="title"]').val(data.title);
            $('#gk-store-update-form input[name="api_url"]').val(data.api_url);
            $('#gk-store-update-form input[name="api_token"]').val(data.api_token);
            $('#gk-store-update-form input[name="api_key"]').val(data.api_key);
        });
    });

    $('#gk-store-update-form').on('submit', function(e) {
        $('#gk-store-update-form [type=submit]').bootstrapBtn('loading');

        $.ajax({
            url: api_url('store-update', 'gkart'),
            type: 'POST',
            data: $('#gk-store-update-form').serialize(),
            success: function(data) {
                setTimeout(function() {
                    window.location.reload(true);
                }, 1000);
            },
            error: function(data) {
                $('#gk-store-update-form [type=submit]').bootstrapBtn('reset');
                displayAjaxError('Add Store', data);
            }
        });

        return false;
    });

    $('.gk-delete-store-btn').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');

        swal({
            title: 'Are you sure?',
            text: 'Please, confirm if you want to delete this store.',
            type: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#DD6B55',
            confirmButtonText: 'Yes, delete it!',
            closeOnConfirm: false
        }, function() {
            $.ajax({
                url: api_url('store', 'gkart') + '?' + $.param({id: storeId}),
                method: 'DELETE',
                success: function() {
                    $('#gk-store-row-' + storeId).hide();
                    swal('Deleted!', 'The store has been deleted.', 'success');
                }
            });
        });
    });

    $('.gkart-verify-api-url').click(function (e) {
        e.preventDefault();

        $(this).bootstrapBtn('loading');

        $.ajax({
            url: api_url('store-verify', 'gkart'),
            type: 'GET',
            data: {
                store: $(this).attr('data-store-id')
            },
            context: {
                btn: $(this)
            },
            success: function (data) {
                swal('API URL', 'The API URL is working properly for GrooveKart store:\n' + data.store, 'success');
            },
            error: function (data) {
                displayAjaxError('API URL', data);
            },
            complete: function () {
                this.btn.bootstrapBtn('reset');
            }
        });
    });

    $('.bigcommerce-delete-store-btn').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');

        swal({
            title: 'Are you sure?',
            text: 'Please, confirm if you want to delete this store.',
            type: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#DD6B55',
            confirmButtonText: 'Yes, delete it!',
            closeOnConfirm: false
        }, function() {
            $.ajax({
                url: api_url('store', 'bigcommerce') + '?' + $.param({id: storeId}),
                method: 'DELETE',
                success: function() {
                    $('#bigcommerce-store-row-' + storeId).hide();
                    swal('Deleted!', 'The store has been deleted.', 'success');
                }
            });
        });
    });

    $('.bigcommerce-verify-api-url').click(function (e) {
        e.preventDefault();

        $.ajax({
            url: api_url('store-verify', 'bigcommerce'),
            type: 'GET',
            data: {
                store: $(this).data('store-id')
            },
            context: {
                btn: $(this)
            },
            success: function (data) {
                swal('API URL', 'The API URL is working properly for BigCommerce store:\n' + data.store, 'success');
            },
            error: function (data) {
                displayAjaxError('API URL', data);
            },
            complete: function () {
            }
        });
    });

    $('#chq-store-create-form').ajaxForm({
        target: '#chq-store-create-form',
        clearForm: true,
        data: {csrfmiddlewaretoken: Cookies.get('csrftoken')},
        success: function(responseText, statusText, xhr, $form) {
            if (xhr.status == 204) {
                window.location.reload();
            }
        }
    });

    $('#chq-store-update-form').ajaxForm({
        target: '#chq-store-update-form',
        clearForm: true,
        data: {csrfmiddlewaretoken: Cookies.get('csrftoken')},
        success: function(responseText, statusText, xhr, $form) {
            if (xhr.status == 204) {
                window.location.reload();
            }
        }
    });

    $('#fb-mp-create-form').on('submit', function(e) {
        e.preventDefault();
        $('#fb-mp-create-form [type=submit]').bootstrapBtn('loading');

        $.ajax({
            url: api_url('store-add', 'fb_marketplace'),
            type: 'POST',
            data: $('#fb-mp-create-form').serialize(),
            success: function(data) {
                swal('Add Store', 'The Facebook Marketplace store has been added successfully', 'success');
                window.location.reload();
            },
            error: function(data) {
                $('#fb-mp-create-form [type=submit]').bootstrapBtn('reset');
                displayAjaxError('Add Store', data);
            }
        });

        return false;
    });

    // $('.woo-edit-store-btn').click(function(e) {
    //     e.preventDefault();
    //     var storeId = $(this).data('store-id');
    //     $.get(api_url('store', 'woo'), {id: storeId}).done(function(data) {
    //         $('#woo-store-update-modal').modal('show');
    //         $('#woo-store-update-form input[name="id"]').val(data.id);
    //         $('#woo-store-update-form input[name="title"]').val(data.title);
    //         $('#woo-store-update-form input[name="api_url"]').val(data.api_url);
    //         $('#woo-store-update-form input[name="api_key"]').val(data.api_key);
    //         $('#woo-store-update-form input[name="api_password"]').val(data.api_password);
    //     });
    // });
    //
    // $('#woo-store-update-form').on('submit', function(e) {
    //     $('#woo-store-update-form [type=submit]').bootstrapBtn('loading');
    //
    //     $.ajax({
    //         url: api_url('store-update', 'woo'),
    //         type: 'POST',
    //         data: $('#woo-store-update-form').serialize(),
    //         success: function(data) {
    //             setTimeout(function() {
    //                 window.location.reload(true);
    //             }, 1000);
    //         },
    //         error: function(data) {
    //             $('#woo-store-update-form [type=submit]').bootstrapBtn('reset');
    //             displayAjaxError('Add Store', data);
    //         }
    //     });
    //
    //     return false;
    // });
    //
    // $('.woo-delete-store-btn').click(function(e) {
    //     e.preventDefault();
    //     var storeId = $(this).data('store-id');
    //
    //     swal({
    //         title: 'Are you sure?',
    //         text: 'Please, confirm if you want to delete this store.',
    //         type: 'warning',
    //         showCancelButton: true,
    //         confirmButtonColor: '#DD6B55',
    //         confirmButtonText: 'Yes, delete it!',
    //         closeOnConfirm: false
    //     }, function() {
    //         $.ajax({
    //             url: api_url('store', 'woo') + '?' + $.param({id: storeId}),
    //             method: 'DELETE',
    //             success: function() {
    //                 $('#woo-store-row-' + storeId).hide();
    //                 swal('Deleted!', 'The store has been deleted.', 'success');
    //             }
    //         });
    //     });
    // });
    //
    // $('.woo-verify-api-url').click(function (e) {
    //     e.preventDefault();
    //
    //     $.ajax({
    //         url: api_url('store-verify', 'woo'),
    //         type: 'GET',
    //         data: {
    //             store: $(this).data('store-id')
    //         },
    //         context: {
    //             btn: $(this)
    //         },
    //         success: function (data) {
    //             swal('API URL', 'The API URL is working properly for WooCommerce store:\n' + data.store, 'success');
    //         },
    //         error: function (data) {
    //             displayAjaxError('API URL', data);
    //         },
    //         complete: function () {
    //         }
    //     });
    // });

    $('#ebay-store-create-submit-btn').click(function(e) {
        if (typeof(Pusher) === 'undefined') {
            toastr.error('This could be due to using Adblocker extensions<br>' +
                'Please whitelist Dropified website and reload the page<br>' +
                'Contact us for further assistance',
                'Pusher service is not loaded', {timeOut: 0});
            return;
        }

        var buttonEl = $(this);
        buttonEl.bootstrapBtn('loading');
        var pusher = new Pusher(sub_conf.key);
        var channel = pusher.subscribe(sub_conf.channel);

        channel.bind('ebay-store-add', function(data) {
            buttonEl.bootstrapBtn('reset');
            pusher.unsubscribe(channel);

            if (data.success) {
                window.location.href = data.auth_url;
            } else {
                displayAjaxError('Add eBay Store', data);
            }
        });

        channel.bind('sd-config-setup', function(data) {
            if (!data.success) {
                buttonEl.bootstrapBtn('reset');
                pusher.unsubscribe(channel);
                displayAjaxError('Add eBay Store', data);
            }
        });

        channel.bind('pusher:subscription_succeeded', function() {
            $.ajax({
                url: api_url('store-add', 'ebay'),
                type: 'GET',
                success: function(data) {},
                error: function(data, status) {
                    buttonEl.bootstrapBtn('reset');
                    pusher.unsubscribe(channel);
                    if (status === 'timeout') {
                        displayAjaxError('Add Store', 'Request timed out. Please try again');
                    } else {
                        displayAjaxError('Add Store', data);
                    }
                },
            });
        });
    });

    $('#fb-store-create-submit-btn').click(function(e) {
        if (typeof(Pusher) === 'undefined') {
            toastr.error('This could be due to using Adblocker extensions<br>' +
                'Please whitelist Dropified website and reload the page<br>' +
                'Contact us for further assistance',
                'Pusher service is not loaded', {timeOut: 0});
            return;
        }

        var buttonEl = $(this);
        buttonEl.bootstrapBtn('loading');
        var pusher = new Pusher(sub_conf.key);
        var channel = pusher.subscribe(sub_conf.channel);

        channel.bind('fb-store-add', function(data) {
            buttonEl.bootstrapBtn('reset');
            pusher.unsubscribe(channel);

            if (data.success) {
                window.location.href = data.auth_url;
            } else {
                displayAjaxError('Add Facebook Store', data);
            }
        });

        channel.bind('sd-config-setup', function(data) {
            if (!data.success) {
                buttonEl.bootstrapBtn('reset');
                pusher.unsubscribe(channel);
                displayAjaxError('Add Facebook Store', data);
            }
        });

        channel.bind('pusher:subscription_succeeded', function() {
            $.ajax({
                url: api_url('store-add', 'fb'),
                type: 'GET',
                success: function(data) {},
                error: function(data, status) {
                    buttonEl.bootstrapBtn('reset');
                    pusher.unsubscribe(channel);
                    if (status === 'timeout') {
                        displayAjaxError('Add Facebook Store', 'Request timed out. Please try again');
                    } else {
                        displayAjaxError('Add Facebook Store', data);
                    }
                },
            });
        });
    });


    $('#google-store-create-submit-btn').click(function(e) {
        if (typeof(Pusher) === 'undefined') {
            toastr.error('This could be due to using Adblocker extensions<br>' +
                'Please whitelist Dropified website and reload the page<br>' +
                'Contact us for further assistance',
                'Pusher service is not loaded', {timeOut: 0});
            return;
        }

        var buttonEl = $(this);
        buttonEl.bootstrapBtn('loading');
        var pusher = new Pusher(sub_conf.key);
        var channel = pusher.subscribe(sub_conf.channel);

        channel.bind('google-store-add', function(data) {
            buttonEl.bootstrapBtn('reset');
            pusher.unsubscribe(channel);

            if (data.success) {
                window.location.href = data.auth_url;
            } else {
                displayAjaxError('Add Google Store', data);
            }
        });

        channel.bind('sd-config-setup', function(data) {
            if (!data.success) {
                buttonEl.bootstrapBtn('reset');
                pusher.unsubscribe(channel);
                displayAjaxError('Add Google Store', data);
            }
        });

        channel.bind('pusher:subscription_succeeded', function() {
            $.ajax({
                url: api_url('store-add', 'google'),
                type: 'GET',
                success: function(data) {},
                error: function(data, status) {
                    buttonEl.bootstrapBtn('reset');
                    pusher.unsubscribe(channel);
                    if (status === 'timeout') {
                        displayAjaxError('Add Google Store', 'Request timed out. Please try again');
                    } else {
                        displayAjaxError('Add Google Store', data);
                    }
                },
            });
        });
    });

    $('.ebay-delete-store-btn').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');

        swal({
            title: 'Are you sure?',
            text: 'Please, confirm that you want to delete this store. This action cannot be undone.',
            type: 'warning',
            showCancelButton: true,
            showLoaderOnConfirm: true,
            confirmButtonColor: '#DD6B55',
            confirmButtonText: 'Yes, delete it!',
            closeOnConfirm: false
        }, function() {
            $.ajax({
                url: api_url('store', 'ebay') + '?' + $.param({id: storeId}),
                method: 'DELETE',
                success: function() {
                    $('#ebay-store-row-' + storeId).hide();
                    swal('Deleted!', 'The store has been deleted.', 'success');
                },
                error: function(data) {
                    displayAjaxError('Delete Store', data);
                }
            });
        });
    });

    $('.ebay-verify-api-url').click(function (e) {
        e.preventDefault();

        $.ajax({
            url: api_url('store-verify', 'ebay'),
            type: 'GET',
            data: {
                store: $(this).data('store-id')
            },
            context: {
                btn: $(this)
            },
            success: function (data) {
                swal('API URL', 'The API URL is working properly for eBay store:\n' + data.store, 'success');
            },
            error: function (data) {
                displayAjaxError('API URL', data);
            },
            complete: function () {
            }
        });
    });

    $('.reauthorize-ebay-store').click(function(e) {
        e.preventDefault();
        if (typeof(Pusher) === 'undefined') {
            toastr.error('This could be due to using Adblocker extensions<br>' +
                'Please whitelist Dropified website and reload the page<br>' +
                'Contact us for further assistance',
                'Pusher service is not loaded', {timeOut: 0});
            return;
        }

        var buttonEl = $(this);
        buttonEl.bootstrapBtn('loading');

        var pusher = new Pusher(sub_conf.key);
        var channel = pusher.subscribe(sub_conf.channel);

        channel.bind('ebay-reauthorize-store', function(data) {
            buttonEl.bootstrapBtn('reset');
            pusher.unsubscribe(channel);

            if (data.success) {
                window.location.href = data.auth_url;
            } else {
                displayAjaxError('Reauthorize eBay store', data);
            }
        });

        channel.bind('pusher:subscription_succeeded', function() {
            $.ajax({
                url: api_url('reauthorize-store', 'ebay') + '?' + $.param({store: buttonEl.attr('data-store-id')}),
                type: 'GET',
                success: function(data) {},
                error: function(data, status) {
                    buttonEl.bootstrapBtn('reset');
                    pusher.unsubscribe(channel);
                    displayAjaxError('Reauthorize eBay store', data);
                },
            });
        });
    });

    $('.reauthorize-fb-store').click(function(e) {
        e.preventDefault();
        if (typeof(Pusher) === 'undefined') {
            toastr.error('This could be due to using Adblocker extensions<br>' +
                'Please whitelist Dropified website and reload the page<br>' +
                'Contact us for further assistance',
                'Pusher service is not loaded', {timeOut: 0});
            return;
        }

        var buttonEl = $(this);
        buttonEl.bootstrapBtn('loading');

        var pusher = new Pusher(sub_conf.key);
        var channel = pusher.subscribe(sub_conf.channel);

        channel.bind('fb-reauthorize-store', function(data) {
            buttonEl.bootstrapBtn('reset');
            pusher.unsubscribe(channel);

            if (data.success) {
                window.location.href = data.auth_url;
            } else {
                displayAjaxError('Reauthorize Facebook store', data);
            }
        });

        channel.bind('pusher:subscription_succeeded', function() {
            $.ajax({
                url: api_url('reauthorize-store', 'fb') + '?' + $.param({store: buttonEl.attr('data-store-id')}),
                type: 'GET',
                success: function(data) {},
                error: function(data, status) {
                    buttonEl.bootstrapBtn('reset');
                    pusher.unsubscribe(channel);
                    displayAjaxError('Reauthorize Facebook store', data);
                },
            });
        });
    });

    $('.reauthorize-google-store').click(function(e) {
        e.preventDefault();
        if (typeof(Pusher) === 'undefined') {
            toastr.error('This could be due to using Adblocker extensions<br>' +
                'Please whitelist Dropified website and reload the page<br>' +
                'Contact us for further assistance',
                'Pusher service is not loaded', {timeOut: 0});
            return;
        }

        var buttonEl = $(this);
        buttonEl.bootstrapBtn('loading');

        var pusher = new Pusher(sub_conf.key);
        var channel = pusher.subscribe(sub_conf.channel);

        channel.bind('google-reauthorize-store', function(data) {
            buttonEl.bootstrapBtn('reset');
            pusher.unsubscribe(channel);

            if (data.success) {
                window.location.href = data.auth_url;
            } else {
                displayAjaxError('Reauthorize Google store', data);
            }
        });

        channel.bind('pusher:subscription_succeeded', function() {
            $.ajax({
                url: api_url('reauthorize-store', 'google') + '?' + $.param({store: buttonEl.attr('data-store-id')}),
                type: 'GET',
                success: function(data) {},
                error: function(data, status) {
                    buttonEl.bootstrapBtn('reset');
                    pusher.unsubscribe(channel);
                    displayAjaxError('Reauthorize Google store', data);
                },
            });
        });
    });


    function handleEbayAdvancedSettingsLoad(data) {
        var generateOptionHtml = function(option, currentSelection) {
            var selectedOption = currentSelection === option.profileId ? ' selected="selected"' : '';
            return '<option value="' + option.profileId + '"' + selectedOption + '>' + option.profileName + '</option>';
        };

        // Payment Profile Option selection
        var allPaymentOptions = data.options.payment_profile_options.map(function(option) {
            return generateOptionHtml(option, data.settings.payment_profile_id);
        });
        allPaymentOptions.unshift(generateOptionHtml({
            profileId: '',
            profileName: 'Select Payment Policy...'
        }, data.settings.payment_profile_id));
        $('#ebay_payment_profile_default').html(allPaymentOptions);

        // Return Profile Option selection
        var allReturnOptions = data.options.return_profile_options.map(function(option) {
            return generateOptionHtml(option, data.settings.return_profile_id);
        });
        allReturnOptions.unshift(generateOptionHtml({
            profileId: '',
            profileName: 'Select Return Policy...'
        }, data.settings.return_profile_id));
        $('#ebay_return_profile_default').html(allReturnOptions);

        // Shipping Profile Option selection
        var allShippingOptions = data.options.shippping_profile_options.map(function(option) {
            return generateOptionHtml(option, data.settings.shipping_profile_id);
        });
        allShippingOptions.unshift(generateOptionHtml({
            profileId: '',
            profileName: 'Select Shipping Policy...'
        }, data.settings.shipping_profile_id));
        $('#ebay_shipment_profile_default').html(allShippingOptions);

        // Site ID selection
        var ebaySiteIdField = $('#ebay_site_id');
        ebaySiteIdField.empty();
        ebaySiteIdField.append($("<option></option>").attr("value", '').text('Select eBay Site ID...'));
        $.each(data.options.site_id_options, function(index, site_id) {
            $('#ebay_site_id').append($("<option></option>").attr("value", site_id[0]).text(site_id[1]));
            if (site_id[0] == data.settings.ebay_siteid) {
                 $('#ebay_site_id option').prop("selected", "true");
            }
        });
    }

    $('.ebay-store-settings-btn').click(function(e) {
        e.preventDefault();

        if (typeof(Pusher) === 'undefined') {
            toastr.error('This could be due to using Adblocker extensions<br>' +
                'Please whitelist Dropified website and reload the page<br>' +
                'Contact us for further assistance',
                'Pusher service is not loaded', {timeOut: 0});
            return;
        }
        var pusher = new Pusher(sub_conf.key);
        var channel = pusher.subscribe(sub_conf.channel);

        var modalTitleEl = $('#ebay-store-update-modal .modal-title');
        var buttonEl = $(this);
        var formContainerEl = $('#ebay-store-settings-main-container');
        var loadingContainerEl = $('#ebay-loading-container');
        var updateSettingsButtonEl = $('#ebay-update-settings-modal-btn');
        var storeId = buttonEl.attr('data-store-id');
        var storeName = buttonEl.attr('data-store-username');

        modalTitleEl.text(storeName ? storeName + ' eBay Advanced Settings' : 'eBay Store Advanced Settings');
        buttonEl.bootstrapBtn('loading');
        updateSettingsButtonEl.prop('disabled', true);
        loadingContainerEl.show();
        formContainerEl.hide();

        $('#ebay_site_id').html('<option value="">No site IDs found.</option>');
        $('#ebay_payment_profile_default').html('<option value="">No policies found.</option>');
        $('#ebay_return_profile_default').html('<option value="">No policies found.</option>');
        $('#ebay_shipment_profile_default').html('<option value="">No policies found.</option>');
        $('#ebay_settings_store_id').val(storeId);


        function handleError(data) {
            buttonEl.bootstrapBtn('reset');
            loadingContainerEl.hide();
            formContainerEl.show();
            displayAjaxError('Advanced eBay Settings', data);
        }

        channel.bind('ebay-business-policies-sync', function(data) {
            if (data.store_id == storeId) {
                pusher.unsubscribe(channel);

                if (data.success) {
                    $.ajax({
                        url: api_url('advanced-settings', 'ebay') + '?' + $.param({store: storeId}),
                        type: 'GET',
                        success: function(data) {
                            buttonEl.bootstrapBtn('reset');
                            updateSettingsButtonEl.prop('disabled', false);
                            handleEbayAdvancedSettingsLoad(data);
                            loadingContainerEl.hide();
                            formContainerEl.show();
                        },
                        error: function(data, status) {
                            handleError(data);
                        },
                    });
                } else {
                    handleError(data);
                }


            }
        });

        channel.bind('pusher:subscription_succeeded', function() {
            $.ajax({
                url: api_url('business-policies-sync', 'ebay') + '?' + $.param({store: storeId}),
                type: 'GET',
                success: function(data) {},
                error: function(data, status) {
                    handleError(data);
                    pusher.unsubscribe(channel);
                },
            });
        });

        $("#ebay-store-update-modal").modal('show');
    });

    $('form#ebay-store-update-settings-form').submit(function (e) {
        e.preventDefault();

        if (typeof(Pusher) === 'undefined') {
            toastr.error('This could be due to using Adblocker extensions<br>' +
                'Please whitelist Dropified website and reload the page<br>' +
                'Contact us for further assistance',
                'Pusher service is not loaded', {timeOut: 0});
            return;
        }
        var pusher = new Pusher(sub_conf.key);
        var channel = pusher.subscribe(sub_conf.channel);

        var buttonEl = $('#ebay-update-settings-modal-btn');
        buttonEl.bootstrapBtn('loading');
        var storeId = $('#ebay_settings_store_id').val();
        var config = $(this).serialize();

        channel.bind('ebay-advanced-settings-update', function(data) {
            if (data.store_id == storeId) {
                buttonEl.bootstrapBtn('reset');
                pusher.unsubscribe(channel);

                if (data.success) {
                    $('#ebay-store-update-modal').modal('hide');
                    toastr.success('Store information updated', 'Advanced eBay Settings');
                } else {
                    displayAjaxError('Advanced eBay Settings', data);
                }
            }
        });

        channel.bind('pusher:subscription_succeeded', function() {
            $.ajax({
                url: api_url('advanced-settings', 'ebay'),
                type: 'POST',
                data: config,
                success: function (data) {},
                error: function (data) {
                    buttonEl.bootstrapBtn('reset');
                    pusher.unsubscribe(channel);
                    displayAjaxError('Advanced eBay Settings', data);
                },
            });
        });
    });

    $('.fb-edit-store-btn').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');
        var storeTitle = $(this).data('store-title');
        $('#fb-store-update-modal').modal('show');
        $('#fb-store-update-form input[name="id"]').val(storeId);
        $('#fb-store-update-form input[name="title"]').val(storeTitle);
    });

    $('#fb-store-update-form').on('submit', function(e) {
        $('#fb-store-update-form [type=submit]').bootstrapBtn('loading');

        $.ajax({
            url: api_url('store-update', 'fb'),
            type: 'POST',
            data: $('#fb-store-update-form').serialize(),
            success: function(data) {
                setTimeout(function() {
                    window.location.reload();
                }, 1000);
            },
            error: function(data) {
                $('#fb-store-update-form [type=submit]').bootstrapBtn('reset');
                displayAjaxError('Edit Store', data);
            }
        });

        return false;
    });

    $('.fb-delete-store-btn').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');

        swal({
            title: 'Are you sure?',
            text: 'Please, confirm that you want to delete this store. This action cannot be undone.',
            type: 'warning',
            showCancelButton: true,
            showLoaderOnConfirm: true,
            confirmButtonColor: '#DD6B55',
            confirmButtonText: 'Yes, delete it!',
            closeOnConfirm: false
        }, function() {
            $.ajax({
                url: api_url('store', 'fb') + '?' + $.param({id: storeId}),
                method: 'DELETE',
                success: function() {
                    $('#fb-store-row-' + storeId).hide();
                    swal('Deleted!', 'The store has been deleted.', 'success');
                },
                error: function(data) {
                    displayAjaxError('Delete Store', data);
                }
            });
        });
    });


    $('.google-delete-store-btn').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');

        swal({
            title: 'Are you sure?',
            text: 'Please, confirm that you want to delete this store. This action cannot be undone.',
            type: 'warning',
            showCancelButton: true,
            showLoaderOnConfirm: true,
            confirmButtonColor: '#DD6B55',
            confirmButtonText: 'Yes, delete it!',
            closeOnConfirm: false
        }, function() {
            $.ajax({
                url: api_url('store', 'google') + '?' + $.param({id: storeId}),
                method: 'DELETE',
                success: function() {
                    $('#google-store-row-' + storeId).hide();
                    swal('Deleted!', 'The store has been deleted.', 'success');
                },
                error: function(data) {
                    displayAjaxError('Delete Store', data);
                }
            });
        });
    });

    $('.filter-store-btn').click(function (e) {
        e.preventDefault();

        $('tr.store-item').each(function (i, el) {
            if($(e.target).prop('shown') || $(el).attr('store-type') === $(e.target).attr('filter-store')) {
                $(el).show();
            } else {
                $(el).hide();
            }
        });

        $(e.target).prop('shown', !$(e.target).prop('shown'));
        $('.filter-store-btn').each(function (j, storeTr) {
            if(e.target !== storeTr) {
                $(storeTr).prop('shown', false);
            }
        });
    });

    $('.del-aliexpress-account').on('click', function(e) {
        e.preventDefault();

        $.ajax({
            url: api_url('account', 'aliexpress') + '?' + $.param({account: $(e.currentTarget).data('account')}),
            method: 'DELETE',
        }).done(function(data) {
            window.location.reload();
        }).error(function(data) {
            displayAjaxError('Delete Aliexpress Account', data);
        });
    });

    $(function () {
        showDescriptionHelp();
        $('#auto_shopify_fulfill').trigger('change');

        var elems = Array.prototype.slice.call(document.querySelectorAll('.js-switch'));
        elems.forEach(function(html) {
            var switchery = new Switchery(html, {
                color: '#93c47d',
                size: 'small'
            });
        });

        dragula([document.getElementById('stores-table-body')], {
                moves: function(el, container, handle) {
                    return (/order\-handle/).test(handle.className);
                }
            })
            .on('drag', function(el) {
                $(el).css('cursor', 'move').find('td').filter(function() {
                    return !$(this).hasClass('drag-show');
                }).children().hide();
            }).on('drop', function(el) {
                $(el).css('cursor', 'inherit').find('td').filter(function() {
                    return !$(this).hasClass('drag-show');
                }).children().show();

                var data = {};
                $('#stores-table-body .store-item').each(function(i, el) {
                    data[$(el).attr('store-id') + ',' + $(el).attr('store-type')] = i;
                });

                $.ajax({
                    url: api_url('store-order', 'all'),
                    type: 'POST',
                    data: data,
                    dataType: 'json',
                    success: function(data) {},
                    error: function(data) {},
                });
            }).on('over', function(el, container) {
                $(el).css('cursor', 'move');
            }).on('out', function(el, container) {
                $(el).css('cursor', 'inherit');
            });

        $('#select-section input[type="radio"]').iCheck({
            radioClass : 'iradio_square-blue',
            increaseArea : '20%'
        });

        $('.change-store-orders').click(function(e) {
            e.preventDefault();

            $('.order-handle').toggle();
        });

        setTimeout(function() {
            try {
                editor_sync_content();

                setup_full_editor('default_desc', false, 'default_desc', true);
            } catch(e) {}
        }, 1000);

        $(".tag-it").tagit({
            allowSpaces: true
        });

        $.contextMenu({
            selector: '.store-link',
            trigger: 'left',
            build: function($trigger, e) {
                e.preventDefault();

                var type = $(e.target).parents('tr').attr('store-type');
                var id = $(e.target).parents('tr').attr('store-id');

                var items = {};
                items["saved-products"] = {name: "Saved Products"};
                items["connected-products"] = {name: "Connected Products"};
                items["boards"] = {name: "Boards"};
                items["sep1"] = "---------";
                items["orders"] = {name: "Orders"};
                items["tracking"] = {name: "Tracking"};
                items["sep2"] = "---------";

                if (type === 'shopify') {
                    items["profits"] = {name: "Profits Dashboard"};
                    items["alerts"] = {name: "Alerts"};
                }

                items["product-feeds"] = {name: "Products Feed"};

                if (type === "fb-marketplace") {
                    items = {};
                    items["saved-products"] = {name: "Saved Products"};
                }

                return {
                    callback: function(key, options) {

                        var slug = (type === 'shopify' ? '' : type) + '/';

                        var products = (type === 'shopify' ? 'product' : 'products');
                        var boards = (type === 'shopify' ? 'boards/list' : 'boards/list');

                        var page = '';
                        if (key === 'saved-products') {
                            page = products + '?store=n&in=' + id;

                        } else if (key === 'connected-products') {
                            page = products + '?store=' + id;

                        } else if (key === 'boards') {
                            page = boards + '?store=' + id;

                        } else if (key === 'orders') {
                            page = 'orders?store=' + id;

                        } else if (key === 'tracking') {
                            page = 'orders/track?store=' + id;

                        } else if (key === 'profits') {
                            page = 'profit-dashboard/?store=' + id;

                        } else if (key === 'alerts') {
                            page = 'products/update?store=' + id;

                        } else if (key === 'product-feeds') {
                            slug = '';
                            if (type !== 'shopify') {
                                page = 'marketing/feeds/' + type + '?store=' + id;
                            } else {
                                page = 'marketing/feeds?store=' + id;
                            }
                        }

                        window.location.href = app_link(slug + page);
                    },
                    items: items
                };
            },
            events: {
                show: function(opt) {
                    setTimeout(function() {
                        opt.$menu.css({
                            'z-index': '10000',
                            'max-height': '300px',
                            'overflow': 'auto',
                        });
                    }, 100);

                    return true;
                }
            }
        });

        if (window.location.hash == '#extension') {
            setTimeout(function () {
                window.extensionSendMessage({
                    subject: 'OpenPage',
                    from: 'website',
                    page: 'options.html',
                });
            }, window.extensionSendMessage ? 100 : 1000);
        }

        var urlParams = new URLSearchParams(window.location.search);
        var newTab = urlParams.get('new_tab');
        if (newTab === '1') {
            $('a', '.store-tables, #side-menu').each(function() {
                $(this).attr('target', '_blank');
            });
        }
    });

    $('.enable-store-btn').click(function (e) {
        var store = $(this).attr('store-type');
        var store_id = $(this).attr('data-store-id');

        swal({
            title: "Enable Store",
            text: "Are you sure that you want to enable this store?",
            type: "warning",
            showCancelButton: true,
            closeOnCancel: true,
            closeOnConfirm: false,
            animation: false,
            showLoaderOnConfirm: true,
            confirmButtonColor: "#DD6B55",
            confirmButtonText: "Enable Store",
            cancelButtonText: "Cancel"
        }, function(isConfirmed) {
            if (!isConfirmed) {
                return;
            }

            $.ajax({
                url: api_url('enable-store', 'ebay'),
                type: 'POST',
                data: {
                    'store': store,
                    'store_id': store_id,
                },
                success: function(data) {
                    swal.close();
                    toastr.success('Store has been enabled.', 'Enable Store');

                    $('.reauthorize-ebay-store').trigger('click');
                },
                error: function(data) {
                    displayAjaxError('Enable Store', data);
                }
            });
        });
    });

    $('#revert_to_v2210311').on('change', function(e) {
        var element = $(this);
        if(element.prop('checked')) {
            swal({
                    title: 'Are you sure you want to switch to our old layout?',
                    text: 'Version 22.10.31.1 is an old version of Dropified and will no longer be getting enhanced.',
                    type: 'warning',
                    html: true,
                    animation: false,
                    showCancelButton: true,
                    confirmButtonColor: '#DD6B55',
                    confirmButtonText: 'Yes',
                    cancelButtonText: 'No',
                    closeOnCancel: false,
                    closeOnConfirm: true,
                    showLoaderOnConfirm: false,
                },
                function (isConfirmed) {
                    if (!isConfirmed) {
                        $('#revert_to_v2210311 + .switchery').click();
                    }
                    swal.close();
                });
        }
    });

})(sub_conf, user_statistics);
