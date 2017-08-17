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
        $('#modal-shopify-send').modal({backdrop: 'static', keyboard: false});
    }
}

$('#shopify-send-btn').click(function(e) {
    var btn = $(this);
    btn.button('loading');
    initializeShopifySendModal(btn);

    var products = [];
    var products_ids = [];

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
        swal('Please select a product(s) first', '', "warning");
        btn.button('reset');
        return;
    }

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
                        setShopifySendModalProgress(products.length, callback_data, req_success, data);
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
