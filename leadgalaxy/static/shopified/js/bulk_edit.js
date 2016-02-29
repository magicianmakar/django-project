/* global $, toastr, swal, displayAjaxError, sendProductToShopify */

(function(config, product) {
'use strict';

$('#save-btn').click(function() {
    var btn = $(this);
    btn.button('loading');

    $.ajax({
        url: '/api/bulk-edit',
        type: 'POST',
        data: $('form#bulk').serialize(),
        success: function(data) {
            if ('status' in data && data.status == 'ok') {
                sendToShopify();
                toastr.success('Saved', 'Bulk Edit');
            } else {
                displayAjaxError('Bulk Edit', data);
            }
        },
        error: function(data) {
            displayAjaxError('Bulk Edit', data);
        },
        complete: function() {
            btn.button('reset');
        }
    });
});

function sendToShopify() {
    var products = [];
    var products_ids = [];


    $('.send-to-shopify').each(function(i, el) {
        if (el.checked) {
            products_ids.push($(el).parents('tr').attr('product-id'));
        }
    });

    if (products_ids.length) {
        $('#modal-shopify-send').modal('show');
    }
}

$('#shopify-send-btn').click(function(e) {
    var products = [];
    var products_ids = [];

    $('#modal-shopify-send .progress').show();

    $('.send-to-shopify').each(function(i, el) {
        if (el.checked) {
            products.push({
                product: $(el).parents('tr').attr('product-id'),
                element: $(el).parents('tr')
            });

            products_ids.push($(el).parents('tr').attr('product-id'));
        }
    });

    if (products.length === 0) {
        //swal('Please select a product(s) first', '', "warning");
        return;
    }

    $('#modal-shopify-send').prop('total_sent_success', 0);
    $('#modal-shopify-send').prop('total_sent_error', 0);
    $('#modal-shopify-send').modal();

    $.ajax({
        url: '/api/products-info',
        type: 'POST',
        data: {
            products: products_ids
        },
        context: {
            products: products
        },
        success: function(data) {
            $.each(products, function(i, el) {
                sendProductToShopify(data[el.product], $('#send-select-store').val(), el.product,
                    function(product, data, callback_data, req_success) {
                        var total_sent_success = parseInt($('#modal-shopify-send').prop('total_sent_success'));
                        var total_sent_error = parseInt($('#modal-shopify-send').prop('total_sent_error'));


                        if (req_success && 'product' in data) {
                            total_sent_success += 1;
                            var chk_el = callback_data.element.find('input[type=checkbox]');
                            chk_el.iCheck('uncheck');
                            chk_el.parents('td').html('<span class="label label-success">Sent</span>');
                        } else {
                            total_sent_error += 1;
                        }

                        $('#modal-shopify-send').prop('total_sent_success', total_sent_success);
                        $('#modal-shopify-send').prop('total_sent_error', total_sent_error);

                        $('#modal-shopify-send .progress-bar-success').css('width', ((total_sent_success * 100.0) / products.length) + '%');
                        $('#modal-shopify-send .progress-bar-danger').css('width', ((total_sent_error * 100.0) / products.length) + '%');

                        if ((total_sent_success + total_sent_error) == products.length) {
                            $('#modal-shopify-send').modal('hide');
                        }
                    }, {
                        'element': el.element,
                        'product': el.product
                    }
                );
            });
        }
    });
});

$(function() {
    $("#product-filter-form").submit(function() {
        $(this).find(":input").filter(function() {
            return !this.value;
        }).attr("disabled", "disabled");
        return true; // ensure form still submits
    });

    $('#filter-type').autocomplete({
        serviceUrl: '/autocomplete/types',
        minChars: 1,
        onSelect: function(suggestion) {}
    });

    $('#filter-tag').autocomplete({
        serviceUrl: '/autocomplete/tags',
        minChars: 1,
        onSelect: function(suggestion) {}
    });
});

})();
