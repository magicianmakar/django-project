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
        $('#modal-shopify-send').modal({backdrop: 'static', keyboard: false});v
    }
}

$('#shopify-send-btn').click(function(e) {
    var products = [];
    var products_ids = [];

    $('#modal-shopify-send .progress').show();
    $('#modal-shopify-send input, #modal-shopify-send select').prop('disabled', true);

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

    $.ajax({
        url: '/api/products-info',
        type: 'GET',
        data: {
            products: products_ids
        },
        context: {
            products: products
        },
        success: function(data) {
            P.map(products, function(el) {
            return new P(function(resolve, reject) {
                sendProductToShopify(data[el.product], $('#send-select-store').val(), el.product,
                    function(product, data, callback_data, req_success) {
                        var total_sent_success = parseInt($('#modal-shopify-send').prop('total_sent_success'));
                        var total_sent_error = parseInt($('#modal-shopify-send').prop('total_sent_error'));


                        if (req_success && 'product' in data) {
                            total_sent_success += 1;
                            var chk_el = callback_data.element.find('input.item-select[type=checkbox]');
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
                            $('#modal-shopify-send .progress').removeClass('progress-striped active');
                            $('#modal-shopify-send .modal-footer').hide();
                        }

                        resolve(product);

                    }, {
                        'element': el.element,
                        'product': el.product
                    }
                );
            });
        }, {
            concurrency: 2
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
        deferRequestBy: 1000,
        onSelect: function(suggestion) {}
    });

    $('#filter-vendor').autocomplete({
        serviceUrl: '/autocomplete/vendor',
        minChars: 1,
        deferRequestBy: 1000,
        onSelect: function(suggestion) {}
    });

    $('#filter-tag').autocomplete({
        serviceUrl: '/autocomplete/tags',
        minChars: 1,
        deferRequestBy: 1000,
        onSelect: function(suggestion) {}
    });
});

})();
