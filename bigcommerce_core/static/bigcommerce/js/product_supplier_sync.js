/* global $, toastr, swal, displayAjaxError */
(function(sub_conf) {
    'use strict';
    if (!sub_conf.channel) {
        return;
    }

    var pusher = new Pusher(sub_conf.key);
    var channel = pusher.subscribe(sub_conf.channel);
    var product_sync_update_tpl;
    var count = 0;
    var success = 0;
    var fail = 0;
    var task;

    channel.bind('products-supplier-sync', function(data) {
        if (!task || data.task != task) {
            return;
        }

        count = data.count;
        success = data.success;
        fail = data.fail;
        if (data.status && data.count > 0) {
            if (data.status == 'ok' && data.error) {
                data['warning'] = data.error;
                delete data['error'];
            }

            var product_el = $(product_sync_update_tpl(data));
            $('#modal-product-supplier-sync .progress-table tbody').append(product_el);
            $('#modal-product-supplier-sync .progress-bar-success').css('width', (success * 100.0 / count) + '%');
            $('#modal-product-supplier-sync .progress-bar-danger').css('width', (fail * 100.0 / count) + '%');
        }

        if (count == success + fail) {
            $('#modal-product-supplier-sync .update-progress .pending-msg').hide();
            $('#modal-product-supplier-sync .update-progress .complete-msg').show();
            $('#modal-product-supplier-sync input').prop('disabled', false);
            $('#modal-product-supplier-sync .start-update-btn').show();
            $('#modal-product-supplier-sync .stop-update-btn').hide();
        }
    });

    product_sync_update_tpl = Handlebars.compile($("#product-sync-update-template").html());

    $('.product-supplier-sync-btn').click(function(e) {
        e.preventDefault();
        $('#modal-product-supplier-sync').modal({
            backdrop: 'static',
            keyboard: false
        });
    });

    $('#modal-product-supplier-sync .sync_price').on('ifChanged', function(e) {
        if (e.target.checked) {
            $('#modal-product-supplier-sync .sync_price_option').show();
        } else {
            $('#modal-product-supplier-sync .sync_price_option').hide();
        }
    });

    $('#modal-product-supplier-sync .start-update-btn').click(function(e) {
        e.preventDefault();

        var post_data = {
            store: $(e.target).attr('data-store'),
            price_markup: $('#modal-product-supplier-sync .price_markup').val(),
            compare_markup: $('#modal-product-supplier-sync .compare_markup').val(),
            products: [],
        };

        if ($('#modal-product-supplier-sync .sync_inventory').is(':checked')) {
            post_data['sync_inventory'] = 1;
        }
        if ($('#modal-product-supplier-sync .sync_price').is(':checked')) {
            post_data['sync_price'] = 1;
        }
        if (!post_data['sync_inventory'] && !post_data['sync_price']) {
            swal(
                'No sync option is selected',
                'Please select "Update Products Price" or "Update Products Inventory" or both',
                'warning');

            return;
        }

        $('input.item-select[type=checkbox]').each(function(i, el) {
            if (el.checked) {
                post_data.products.push($(el).parents('.product-box').attr('product-id'));
            }
        });

        if (!post_data.products.length) {
            swal('No product selected', 'Please select products.', 'warning');
            return;
        } else {
            post_data.products = post_data.products.join(',');
        }

        $.ajax({
            url: api_url('products-supplier-sync', 'bigcommerce'),
            type: 'POST',
            data: post_data,
        }).done(function(data) {
            task = data.task;
            $('#modal-product-supplier-sync .progress-table tbody').html('');
            $('#modal-product-supplier-sync .progress-bar-success').css('width', '0%');
            $('#modal-product-supplier-sync .progress-bar-danger').css('width', '0%');
            $('#modal-product-supplier-sync .update-progress').show();
            $('#modal-product-supplier-sync .update-progress .pending-msg').show();
            $('#modal-product-supplier-sync .update-progress .complete-msg').hide();
            $('#modal-product-supplier-sync input').prop('disabled', 'disabled');
            $('#modal-product-supplier-sync .start-update-btn').hide();
            $('#modal-product-supplier-sync .stop-update-btn').show();

        }).fail(function(data) {
            displayAjaxError('Product Sync', data);
        });
    });

    $('#modal-product-supplier-sync .stop-update-btn').click(function(e) {
        e.preventDefault();
        $.ajax({
            url: '/api/products-supplier-sync-stop',
            type: 'POST',
            data: {
                store: $(e.target).attr('data-store')
            },
        }).done(function(data) {
            $('#modal-product-supplier-sync input').prop('disabled', null);
            $('#modal-product-supplier-sync .start-update-btn').show();
            $('#modal-product-supplier-sync .stop-update-btn').hide();

        }).fail(function(data) {
            displayAjaxError('Product Sync', data);
        });
    });
})(sub_conf);
