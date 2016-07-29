/* global $, toastr, swal, displayAjaxError */

(function() {
'use strict';

$('.add-store-btn').click(function (e) {
    e.preventDefault();

    if(/free plan/i.test($(this).data('plan'))) {
        return swal({
            title: 'Add Store',
            text: 'You are currently using the Free Plan from Shopified App. <br/>' +
                  'This plan does not support connecting Shopify stores. <br/>' +
                  'Please upgrade to a paid plan. <br/>For more information, ' +
                  'contact <a href="mailto:support@shopifiedapp.com">support@shopifiedapp.com</a>',
            type: 'warning',
            animation: false,
            html: true
        });
    }

    $('#add-store').show();
    $('#update-store').hide();

    $('#store-name').val('');
    $('#store-url').val('');

    $('#modal-install-form').modal('show');
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
        $(this).button('loading');
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

    $('#add-store').button('loading');

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
            $('#add-store').button('reset');
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

    btn.button('loading');

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
            } else {
                displayAjaxError('Store update', data);
            }
        },
        error: function (data) {
            displayAjaxError('Store update', data);
        },
        complete: function () {
            this.btn.button('reset');
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

$('.verify-api-url').click(function (e) {
    $(this).button('loading');

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
            this.btn.button('reset');
        }
    });
});

$('input[name="order_phone_number"]').on('keyup', function() {
    var value = $(this).val();

    $('#phone-invalid').toggle(/[^\d-]/.test(value));
});

$('input[name="order_phone_number"]').trigger('keyup');

$(function () {
    showDescriptionHelp();
    $('#auto_shopify_fulfill').trigger('change');

    var elems = Array.prototype.slice.call(document.querySelectorAll('.js-switch'));
    elems.forEach(function(html) {
        var switchery = new Switchery(html, {
            color: '#1AB394',
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
});

})();