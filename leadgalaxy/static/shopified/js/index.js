/* global $, toastr, swal, displayAjaxError */

(function(config, product) {
'use strict';

$('.add-store-btn').click(function (e) {
    e.preventDefault();
    $('#add-store').show();
    $('#update-store').hide();

    $('#modal-form').modal('show');
});

$('#add-store').click(function(e) {
    var url = $('#store-url').val().match(/[^\*:/]{10,}:[^\*:]{10,}@[^\.]+\.myshopify\.com/);

    if (!url || url.length != 1) {
        alert('API URL is not correct!');
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
                alert(data.error);
                $('#add-store').button('reset');
            } else {
                window.location.href = window.location.href;
            }

        },
        error: function(data) {
            alert('Unknow error!');
            $('#add-store').button('reset');
        }
    });
});


$('.delete-store').click(function (e) {
    document.current_store = $(this).attr('store-id');
    $('#modal-store-move').modal('show');
});

$('#store-move-btn').click(function (e) {
    var btn = $(this);
    var store = parseInt(document.current_store);
    var move_to = parseInt($('#move-select-store').val());

    if (move_to <= 0) {
        swal('Delete Store', 'Please select a store', 'warning');
        return;
    }
    if (move_to == store) {
        swal('Delete Store', 'Please choose an other store ', 'warning');
        return;
    }

    btn.button('loading');

    $.ajax({
        url: '/api/delete-store',
        type: 'POST',
        data: {
            'store': store,
            'move-to': move_to
        },
        success: function(data) {
            if ('error' in data) {
                swal('Delete Store', data.error, 'error');
            } else {
                $('tr[store-id="'+store+'"]').remove();
            }
        },
        error: function(data) {
            swal('Delete Store', 'Server error', 'error');
        },
        complete: function () {
            $('#modal-store-move').modal('hide');
            btn.button('reset');
        }
    });
});

$('form#config-form').submit(function (e) {
    e.preventDefault();

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
                swal('User Config', ('error' in data ? data.error : 'Unknow error'), 'error');
            }
        },
        error: function (data) {
            swal('User Config', 'Server error', 'error');
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

    $('#modal-form').modal('show');

});

$('#update-store').click(function (e) {
    e.preventDefault();

    var store = $('#store-name').attr('store-id');
    var name = $('#store-name').val();
    var url = $('#store-url').val().match(/[^\*:/]{10,}:[^\*:]{10,}@[^\.]+\.myshopify\.com/);

    if (!url || url.length != 1) {
        alert('API URL is not correct!');
        return;
    } else {
        url = 'https://' + url[0];
    }

    $.ajax({
        url: '/api/update-store',
        type: 'POST',
        data: {
            store: store,
            title: name,
            url: url
        },
        context: {},
        success: function (data) {
            if (data.status == 'ok') {
                $('#modal-form').modal('hide');
                toastr.success('Store information updated', 'Store update');
            } else {
                displayAjaxError('Store update', data);
            }
        },
        error: function (data) {
            displayAjaxError('Store update', data);
        },
        complete: function () {
        }
    });
});

$('.show-api-url').click(function (e) {
    e.preventDefault();

    $(this).parent().find('.api-url').toggle();
});

$(function () {
    showDescriptionHelp();
});

})();