/* global $, toastr, swal, displayAjaxError, sendProductToShopify */

(function() {
'use strict';

function changeProductStat(product, stat, callback, erroback) {
    $.ajax({
        url: '/api/product-stat',
        type: 'POST',
        data: {
            product: product,
            sent: stat
        },
        success: function(data) {
            callback(data);
        },
        error: function(data) {
            erroback(data);
        }
    });
}

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
                        swal("Deleted!", "The product has been deleted.", "success");
                    },
                    error: function(data) {
                        swal("Error", "Server side error", "error");
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
        $('#modal-form').modal('show');
        return;
    } else if (action == 'board') {
        $('#modal-board-product').modal('show');
        return;
    } else if (action == 'shopify-send') {
        $('#modal-shopify-send').modal('show');
        return;
    }

    $('#selected-actions').val('');
    $('input.item-select[type=checkbox]').each(function(i, el) {
        if (el.checked) {
            var product = $(el).parents('tr').attr('product-id');
            if (action == 'unsent') {
                changeProductStat(product, 0, function(data) {
                    if (data.status == 'ok') {
                        btn.hide();
                    }
                }, function(data) {
                    alert('Server side error');
                });
            } else if (action == 'sent') {

                changeProductStat(product, 1, function(data) {
                    if (data.status == 'ok') {}
                }, function(data) {
                    alert('Server side error');
                });
            } else if (action == 'delete') {
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
                        alert('Server side error');
                    }
                });
            }

            $(el).iCheck('uncheck');
        }
    });
});

$('#save-changes').click(function(e) {
    var btn = $(this);
    var products = [];

    $('input.item-select[type=checkbox]').each(function(i, el) {
        if (el.checked) {
            products.push($(el).parents('tr').attr('product-id'));
            $(el).iCheck('uncheck');
        }
    });


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
                alert('error' in data ? data.error : 'Server error');
            }
        },
        error: function(data) {
            alert('error' in data ? data.error : 'Server error');
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
        alert('Please select a board.');
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
                alert('error' in data ? data.error : 'Server error');
            }
        },
        error: function(data) {
            alert('error' in data ? data.error : 'Server error');
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

    $(this).button('loading');

    var products = [];
    var products_ids = [];

    $('#modal-shopify-send .progress').show();

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
                        } else {
                            total_sent_error += 1;
                        }

                        $('#modal-shopify-send').prop('total_sent_success', total_sent_success);
                        $('#modal-shopify-send').prop('total_sent_error', total_sent_error);

                        $('#modal-shopify-send .progress-bar-success').css('width', ((total_sent_success * 100.0) / products.length) + '%');
                        $('#modal-shopify-send .progress-bar-danger').css('width', ((total_sent_error * 100.0) / products.length) + '%');

                        callback_data.element.find('input.item-select[type=checkbox]').iCheck('disable');

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
