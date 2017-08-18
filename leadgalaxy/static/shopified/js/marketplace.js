/* global $, toastr, swal, displayAjaxError, sendProductToShopify */

(function() {
'use strict';
var action = 'save'; // import
var targetProducts = [];

function getSelectProduct() {
    var products = [];

    $('input.item-select[type=checkbox]').each(function(i, el) {
        if (el.checked && !el.disabled) {
            products.push($(el).parents('tr').attr('product-id'));
        }
    });

    return products;
}

function setShopifySendModalTitle() {
    $('#modal-shopify-send .modal-title').text(action == 'save' ? 'Save for later' : 'Sending To Shopify');
    $('#modal-shopify-send').modal('show');
}

$('#shopify-close-btn').click(function(e) {
    $('#modal-shopify-send').modal('hide');
});

$('.save-for-later-btn').click(function(e) {
    action = 'save';
    targetProducts = [$(this).attr('product-id')];
    setShopifySendModalTitle();
});

$('.import-btn').click(function(e) {
    action = 'import';
    targetProducts = [$(this).attr('product-id')];
    setShopifySendModalTitle();
});

$('#bulk-save-for-later-btn, #bulk-import-btn').click(function(e) {
    if (this.id == 'bulk-save-for-later-btn') {
        action = 'save';
    } else {
        action = 'import';
    }

    targetProducts = getSelectProduct();
    if (!targetProducts || !targetProducts.length) {
        swal('No product is selected');
        return;
    }

    setShopifySendModalTitle();
});

$('#shopify-send-btn').click(function(e) {
    var btn = $(this);
    btn.button('loading');
    initializeShopifySendModal();

    var store = $('#send-select-store').val();

    var products = [];
    var products_data = [];

    targetProducts.forEach(function(id) {
        products.push({
            product: id,
            element: $('.product-wrapper[product-id=' + id + ']')
        });

        var original_product = null;
        for (var i = 0; i < dropwow_products.length; i++) {
            if (id == dropwow_products[i].id) {
                original_product = dropwow_products[i];
                break;
            }
        }

        if (!original_product) {
            return;
        }

        var options = [];
        var option_id_index = {};
        $.each(original_product.options, function(v, k) {
            var variants = [];
            for (var key in v.variants) {
                if (v.variants.hasOwnProperty(key)) {
                    variants.push(v.variants[key]);
                }
            }

            options.push({
                title: v.option_name,
                values: variants
            });

            option_id_index[v.option_id] = options.length;
        });

        var variants = [];
        $.each(original_product.combinations, function(i, c) {
            var variant = {
                title: c.title,
                price: c.price
            };

            $.each(c.combination, function(option_id, option_value) {
                variant['option' + option_id_index[option_id]] = original_product.options[option_id].variants[option_value];
            });

            variants.push(variant);
        });

        var api_data = {
            'title': original_product.title,
            'description': original_product.description,
            'price': original_product.combinations[0].price,
            'compare_at_price': null,
            'images': $.map(original_product.combinations, function(c) {
                return c.image_path;
            }),
            'original_url': app_link('marketplace/product/', original_product.id),
            'store': {
                url: app_link('marketplace'),
                name: 'Dropwow'
            },
            'type': original_product.category ? original_product.category.label : '',
            'tags': '',
            'vendor': original_product.vendor,
            "published": $('#send-product-visible')[0].checked,
            'weight': '',
            'weight_unit': '',
            'variants_images': {},
            'variants_sku': {},

            'variants': options,
        };
        var req_data = {
            'store': store,
            'data': JSON.stringify(api_data),
            'original': JSON.stringify(original_product),
            'original_id': original_product.id,
            'notes': '',
            'activate': false,
            'b': false,
        };
        products_data.push(req_data);
    });

    if (products.length === 0) {
        swal('Please select a product(s) first', '', "warning");
        btn.button('reset');
        return;
    }

    $.ajax({
        url: '/api/save-for-later-products',
        type: 'POST',
        data: JSON.stringify({
            products: products_data
        }),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        context: {
            products: products
        },
        success: function(data) {
            $.each(products, function(i, el) {
                if (!data[el.product] || !data[el.product]['id']) return;
                if (action == 'save') {
                    setShopifySendModalProgress(products.length, {
                        'element': el.element,
                        'product': el.product
                    }, true, { 'product': el.product });
                } else {
                    sendProductToShopify(data[el.product], $('#send-select-store').val(), data[el.product].id,
                        function(product, data, callback_data, req_success) {
                            setShopifySendModalProgress(products.length, callback_data, req_success, data);
                        }, {
                            'element': el.element,
                            'product': el.product
                        }
                    );
                }
            });
        }
    });
});

$('.filter-btn').click(function(e) {
    e.preventDefault();
    $('#modal-filter').modal('show');
});

})();