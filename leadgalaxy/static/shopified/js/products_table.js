/* global $, toastr, swal, displayAjaxError, sendProductToShopify */

(function() {
'use strict';

$('.delete-product-btn').click(function(e) {
    var btn = $(this);
    var product = btn.attr('product-id');

    swal({
            title: "Delete Product",
            text: "This will remove the product permanently. Are you sure you want to remove this product?",
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
                    url: '/api/product-delete',
                    type: 'POST',
                    data: {
                        product: product,
                    },
                    success: function(data) {
                        btn.parents('tr').remove();

                        swal.close();
                        toastr.success("The product has been deleted.", "Deleted!");
                    },
                    error: function(data) {
                        displayAjaxError('Delete Product', data);
                    }
                });
            }
        });
});

$('#apply-btn').click(function(e) {
    var action = $('#selected-actions').val();
    if (action == 'delete') {
        if (!confirm('Are you sure that you want to permanently delete the selected products?')) {
            return;
        }
    } else if (action == 'edit') {
        productsEditModal(getSelectProduct());
        return;
    } else if (action == 'board') {
        $('#modal-board-product').modal('show');
        return;
    } else if (action == 'shopify-send') {
        $('#modal-shopify-send').modal({backdrop: 'static', keyboard: false});
        return;
    } else {
        return;
    }

    $('#selected-actions').val('');
    $('input.item-select[type=checkbox]').each(function(i, el) {
        if (el.checked) {
            var product = $(el).parents('tr').attr('product-id');
            if (action == 'delete') {
                $.ajax({
                    url: '/api/product-delete',
                    type: 'POST',
                    data: {
                        product: product,
                    },
                    success: function(data) {
                        $(el).parents('tr').remove();
                    },
                    error: function(data) {
                        displayAjaxError('Delete Product', data);
                    }
                });
            }

            $(el).iCheck('uncheck');
        }
    });
});

function getSelectProduct() {
    var products = [];

    $('input.item-select[type=checkbox]').each(function(i, el) {
        if (el.checked) {
            products.push($(el).parents('tr').attr('product-id'));
        }
    });

    return products;
}

$('#modal-products-edit-form #save-changes').click(function(e) {
    var btn = $(this);
    var products = getSelectProduct();

    var data = {
        'products': products
    };

    if ($('#product-price').val().length) {
        data['price'] = $('#product-price').val();
    }

    if ($('#product-compare-at').val().length) {
        data['compare_at'] = $('#product-compare-at').val();
    }

    if ($('#product-type').val().length) {
        data['type'] = $('#product-type').val();
    }

    if ($('#product-tags').val().length) {
        data['tags'] = $('#product-tags').val();
    }

    if ($('#product-weight').val().length) {
        data['weight'] = $('#product-weight').val();
        data['weight_unit'] = $('#product-weight-unit').val();
    }

    btn.button('loading');

    $.ajax({
        url: '/api/product-edit',
        type: 'POST',
        data: data,
        success: function(data) {
            if ('status' in data && data.status == 'ok') {
                window.location.href = window.location.href;
            } else {
                displayAjaxError('Edit Product', data);
            }
        },
        error: function(data) {
            displayAjaxError('Edit Product', data);
        },
        complete: function() {
            btn.button('reset');
        }
    });
});

$('#board-product-send').click(function(e) {
    var btn = $(this);
    var products = [];

    if ($('#selected-board').val().length === 0) {
        swal('Please select a board.');
        return;
    }

    $('input.item-select[type=checkbox]').each(function(i, el) {
        if (el.checked) {
            products.push($(el).parents('tr').attr('product-id'));
            $(el).iCheck('uncheck');
        }
    });

    var data = {
        'board': $('#selected-board').val(),
        'products': products
    };

    btn.button('loading');

    $.ajax({
        url: '/api/board-add-products',
        type: 'POST',
        data: data,
        success: function(data) {
            if ('status' in data && data.status == 'ok') {
                $('#modal-board-product').modal('hide');
            } else {
                displayAjaxError('Board Product', data);
            }
        },
        error: function(data) {
            displayAjaxError('Board Product', data);
        },
        complete: function() {
            btn.button('reset');
        }
    });
});

$("#product-filter-form").submit(function() {
    $(this).find(":input").filter(function() {
        return !this.value;
    }).attr("disabled", "disabled");
    return true; // ensure form still submits
});

$('#shopify-send-btn').click(function(e) {
    var btn = $(this);
    btn.button('loading');
    initializeShopifySendModal();

    var products = [];
    var products_ids = [];

    $('input.item-select[type=checkbox]').each(function(i, el) {
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
