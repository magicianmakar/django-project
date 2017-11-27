/* global $, toastr, swal, displayAjaxError, sendProductToShopify */

(function() {
setup_full_editor('product-description');
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
    if (targetProducts.length == 1) {
        var original_product;
        for (var i = 0; i < dropwow_products.length; i++) {
            if (targetProducts[0] == dropwow_products[i].id) {
                original_product = dropwow_products[i];
                break;
            }
        }

        $('#modal-shopify-send #product-title').val(original_product.title);
        $('#modal-shopify-send #product-price').val(original_product.price);
        $('#modal-shopify-send #product-compare-at').val('');
        $('#modal-shopify-send #product-weight').val('');
        $('#modal-shopify-send #product-type').val(original_product.category ? original_product.category.label : '');
        $('#modal-shopify-send #product-tag').val('');
        $('#modal-shopify-send #product-vendor').val(original_product.vendor);
        CKEDITOR.instances['product-description'].setData(original_product.description);
        $('#modal-shopify-send .product-details').show();
    }
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
        var variant_id_index = {};
        $.each(original_product.options, function(k, v) {
            var values = [];
            for (var i = 0; i < v.variants.length; i++) {
                variant_id_index[v.variants[i].variant_id] = v.variants[i];
                values.push(v.variants[i].variant_name);
            }

            options.push({
                title: v.option_name,
                values: values
            });

            option_id_index[v.option_id] = options.length;
        });

        var title, price, compare_at_price, weight, weight_unit, type, tag, vendor, description;

        if (targetProducts.length == 1 && $('#modal-shopify-send .product-details').is(':visible')) {
            title = $('#modal-shopify-send #product-title').val();
            price = parseFloat($('#modal-shopify-send #product-price').val());
            compare_at_price = $('#modal-shopify-send #product-compare-at').val();
            weight = $('#modal-shopify-send #product-weight').val();
            weight_unit = weight ? $('#modal-shopify-send #product-weight-unit').val() : '';
            type = $('#modal-shopify-send #product-type').val();
            tag = $('#modal-shopify-send #product-tag').val();
            vendor = $('#modal-shopify-send #product-vendor').val();
            description = CKEDITOR.instances['product-description'].getData();
        } else {
            title = original_product.title;
            price = original_product.price;
            compare_at_price = null;
            weight = '';
            weight_unit = '';
            type = original_product.category ? original_product.category.label : '';
            tag = '';
            vendor = '';
            description = original_product.description;
        }

        var variants = [];
        $.each(original_product.combinations, function(i, c) {
            var variant = {};
            var combination = [];

            var modifier = 0;
            $.each(c.combination, function(option_id, variant_id) {
                variant['option' + option_id_index[option_id]] = variant_id_index[variant_id].variant_name;
                var option_variant = {};
                option_variant[option_id] = variant_id;
                combination.push(option_variant);
                modifier = modifier + variant_id_index[variant_id].modifier;
            });
            var variant_price = price + modifier;
            variant_price = Math.round(variant_price * 100) / 100;
            variant['price'] = variant_price;
            variant['quantity'] = c.quantity;
            variant['combination'] = combination;

            variants.push(variant);
        });

        var api_data = {
            'title': title,
            'description': description,
            'price': price,
            'compare_at_price': compare_at_price ? compare_at_price : null,
            'images': $.map(original_product.images, function(c) {
                return c.path;
            }),
            'original_url': app_link(['marketplace/product/', original_product.id]),
            'store': {
                url: app_link('marketplace'),
                name: 'Dropwow'
            },
            'type': type,
            'tags': tag,
            'vendor': vendor,
            "published": $('#send-product-visible')[0].checked,
            'weight': weight,
            'weight_unit': weight_unit,
            'variants_images': {},
            'variants_sku': {},

            'variants': options,
            'combinations': variants,
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
                        'product': data[el.product]['id']
                    }, true, { 'product': el.product });
                } else {
                    sendProductToShopify(data[el.product], $('#send-select-store').val(), data[el.product].id,
                        function(product, data, callback_data, req_success) {
                            setShopifySendModalProgress(products.length, callback_data, req_success, data);
                        }, {
                            'element': el.element,
                            'product': data[el.product]['id']
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