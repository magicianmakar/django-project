(function(sub_conf, user_statistics) {
'use strict';

function syncConfig() {
    window.extensionSendMessage({
        subject: 'SyncUserConfig',
        from: 'website',
        stores: true,
    }, function() {});
}

$('.add-store-btn').click(function (e) {
    e.preventDefault();

    $('#add-store').show();
    $('#update-store').hide();

    $('#store-name').val('');
    $('#store-url').val('');

    $('#modal-install-form').modal('show');
});

$('#install-store-form').on('submit', function(e) {
    $('#install-store').trigger('click');

    return false;
});

$('#install-store').click(function (e) {
    var shop = $('#shop-url').val().trim().match(/(?:https?:\/\/)?(?:[^:]*:[^@]*@)?([^/\.]+)(?:\.myshopify\.com)?/);
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
    var url = $('#store-url').val().match(/[^\*:/]{10,}:[^\*:]{10,}@[^\.]+\.myshopify\.com/);

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
    var url = $('#store-url').val().match(/[^\*:/]{10,}:[^\*:]{10,}@[^\.]+\.myshopify\.com/);

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
            swal('API URL', 'The API URL is working properly for Shopify Store:\n' + data.store, 'success');
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

    $.ajax({
        url: '/api/custom-tracking-url',
        type: 'GET',
        data: {
            store: $(this).attr('store-id')
        },
        success: function(data) {
            $('#custom-tracking-url-input').val(data.tracking_url);
            $('#custom-tracking-url-input').attr('store', data.store);
        },
        error: function(data) {
            displayAjaxError('Custom Tracking URL', data);
        }
    });

    $("#modal-store-tracking-url").modal('show');
});

$('#save-custom-tracking-btn').click(function (e) {
    e.preventDefault();

    var btn = $(this);
    btn.bootstrapBtn('loading');

    var tracking_url = $('#custom-tracking-url-input').val().trim();
    var store = $('#custom-tracking-url-input').attr('store');

    if (tracking_url.length && tracking_url.indexOf('{{tracking_number}}') == -1) {
        swal('Tracking URL', 'Tracking url must include {{tracking_number}}\nsee the example below custom url entry field.', 'error');
        return;
    }

    $.ajax({
        url: '/api/custom-tracking-url',
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
        },
        error: function (data) {
            displayAjaxError('Custom Description', data);
        }
    });

});

$('#description-template-table .delete-template').click(function(e) {
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
});

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

function updateUserStatistics(statistics_data) {
    $.each(statistics_data, function(i, store_info) {
        $('#orders_pending_' + store_info.id).html('').parents('.statistics-link').show(0);
        var saved = $('#products_saved_' + store_info.id).html(store_info.products_saved).parents('.statistics-link');
        if (store_info.products_saved) {
            saved.show(0);
        } else {
            saved.hide(0);
        }

        var connected = $('#products_connected_' + store_info.id).html(store_info.products_connected).parents('.statistics-link');
        if (store_info.products_connected) {
            connected.show(0);
        } else {
            connected.hide(0);
        }
    });
}

if (user_statistics) {
    updateUserStatistics(user_statistics);
} else {
    var pusher = new Pusher(sub_conf.key);
    var channel = pusher.subscribe(sub_conf.channel);
    var pending_order_task_id = null;

    channel.bind('user-statistics-calculated', function(data) {
        if (pending_order_task_id === data.task) {
            $.ajax({
                url: '/api/user-statistics',
                type: 'GET',
                data: {
                    cache_only: true
                },
                success: function(data) {
                    if (data.stores) {
                        updateUserStatistics(data.stores);
                    }
                }
            });
        }
    });

    channel.bind('pusher:subscription_succeeded', function() {
        $.ajax({
            url: '/api/user-statistics',
            type: 'GET',
            success: function(data) {
                if (data.task) {
                    pending_order_task_id = data.task;
                } else if (data.stores) {
                    updateUserStatistics(data.stores);
                }
            }
        });
    });
}

$('#markup-rule-table .delete-rule').click(deleteMarkupRuleClicked);

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
                data[$(el).attr('store-id')] = i;
            });

            $.ajax({
                url: '/api/store-order',
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
