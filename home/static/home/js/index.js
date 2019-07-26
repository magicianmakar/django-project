(function(sub_conf, user_statistics) {
    'use strict';

    isExtensionReady().done(function () {
        $('a.extension-link').hide();
        Cookies.set('ext_installed', 'true');
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
            if ($(this).data('extra')) {
                swal({
                    title: "Additional Store",
                    text: "You are about to add an additional store to your plan for <b>$27/month</b>, Would you like to continue?",
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

    $('#install-store-form').on('submit', function(e) {
        $('#install-store').trigger('click');

        return false;
    });

    $('#install-store').click(function (e) {
        var shop = $('#shop-url').val().trim().match(/(?:https?:\/\/)?(?:[^:]*:[^@]*@)?([^\/\.]+)(?:\.myshopify\.com)?/);
        if (!shop || shop.length != 2) {
            swal('Add Store', 'Store URL is not correct!', 'error');
            return;
        } else {
            shop = shop.pop();
        }

        if($('.add-store-btn').data('extra')) {
            swal({
                title: "Additional Store",
                text: "You are about to add an additional store to your plan for <b>$27/month</b>, Would you like to continue?",
                type: "info",
                html: true,
                showCancelButton: true,
                closeOnCancel: true,
                closeOnConfirm: false,
                animation: false,
                showLoaderOnConfirm: true,
                confirmButtonText: "Yes, Add This Store",
                cancelButtonText: "Cancel"
            }, function(isConfirmed) {
                if (!isConfirmed) {
                    return;
                }

                window.location.href = '/shopify/install/' + shop;
            });
        } else {
            $(this).bootstrapBtn('loading');
            window.location.href = '/shopify/install/' + shop;
        }
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

    $('form#config-form').submit(function (e) {
        e.preventDefault();

        if ($('#phone-invalid').is(':visible')) {
            toastr.error('Phone Number is not valid');
        }

        var config = $(this).serialize();

        $.ajax({
            url: '/api/user-config',
            type: 'POST',
            data: config,
            context: {form: $(this)},
            success: function (data) {
                if (data.status == 'ok') {
                    toastr.success('Saved.','User Config');

                    syncConfig();

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

    $('#fix_aliexpress_address').change(function (e) {
        if(!e.target.checked) {
            $('#fix_aliexpress_city').parents('.option-config-row').hide();
        } else {
            $('#fix_aliexpress_city').parents('.option-config-row').show();
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

        window.location.href = '/shopify/install/' + $(this).attr('store-shop') + '?reinstall=' + $(this).attr('store-id');
    });

    $('.change-tracking-url').click(function(e) {
        e.preventDefault();

        var storeType = $(this).attr('store-type');
        var useDomain = $(this).attr('tracking-domain');
        if (useDomain) {
            $('#custom-tracking-type').text('Domain');
            $('#tracking-url-wrapper').css('display', 'none');
        } else {
            $('#custom-tracking-type').text('URL');
            $('#tracking-url-wrapper').css('display', '');
        }
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

    $('input[name="order_phone_number"]').on('keyup', function() {
        var value = $(this).val();

        $('#phone-invalid').toggle(/[^\d\+-]/.test(value));
    });

    $('input[name="order_phone_number"]').trigger('keyup');


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

    var deleteMarkupRuleClicked = function(e) {
        e.preventDefault();
        var btn = $(this);

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
                    tr.find('.rule-markup_compare_value').text(parseFloat(rule.markup_compare_value).toFixed(2));
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
        console.log('submited');
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
        console.log(store_data);

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
        $('#gk-store-create-form [type=submit]').bootstrapBtn('loading');

        $.ajax({
            url: api_url('store-add', 'gkart'),
            type: 'POST',
            data: $('#gk-store-create-form').serialize(),
            success: function(data) {
                window.location.reload(true);
            },
            error: function(data) {
                $('#gk-store-create-form [type=submit]').bootstrapBtn('reset');
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
            editor_sync_content();

            setup_full_editor('default_desc', false, 'default_desc', true);
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
    });

})(sub_conf, user_statistics);