/* global $, toastr, swal, displayAjaxError, sendProductToShopify */
/* global boardsMenu */

(function(config, product) {
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

$('.sent-btn')
    .mouseenter(function() {
        $('span', this).text("Unsent");
        $(this).toggleClass('btn-success');
        $(this).toggleClass('btn-warning');
    })
    .mouseleave(function() {
        $('span', this).text("Sent");
        $(this).toggleClass('btn-warning');
        $(this).toggleClass('btn-success');
    })
    .click(function(e) {
        var btn = $(this);
        btn.button('loading');


        changeProductStat(btn.attr('product-id'), 0,
            function(data) {
                if ('error' in data) {
                    swal("Error", data.error, "error");
                    btn.button('reset');
                } else {
                    btn.hide();
                }
            },
            function(data) {
                btn.button('reset');
                swal("Error", "Server side error", "error");
            });
    });

$('#apply-btn').click(function(e) {
    var action = $('#selected-actions').val();


    if (action.length === 0) {
        swal('Please select an action first', '', "warning");
        return;
    }

    if (action == 'delete') {
        swal({
                title: "Delete Selected Products",
                text: "This will remove the selected products permanently. Are you sure you want to remove those products?",
                type: "warning",
                showCancelButton: true,
                confirmButtonColor: "#DD6B55",
                confirmButtonText: "Remove Permanently",
                cancelButtonText: "Cancel"
            },
            function(isConfirmed) {
                if (isConfirmed) {
                    $('input[type=checkbox]').each(function(i, el) {
                        if (el.checked) {
                            var product = $(el).parents('.product-box').attr('product-id');
                            $.ajax({
                                url: '/api/product-delete',
                                type: 'POST',
                                data: {
                                    product: product,
                                },
                                success: function(data) {
                                    $(el).parents('.col-md-3').remove();
                                },
                                error: function(data) {
                                    swal("Error", "Server side error", "error");
                                }
                            });

                            $(el).iCheck('uncheck');
                        }
                    });
                }
            });
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
    $('input[type=checkbox]').each(function(i, el) {
        if (el.checked) {
            var product = $(el).parents('.product-box').attr('product-id');
            if (action == 'unsent') {
                var btn = $(el).parents('.product-box').find('.sent-btn');
                btn.button('loading');

                changeProductStat(product, 0, function(data) {
                    if (data.status == 'ok') {
                        btn.hide();
                    }
                }, function(data) {
                    btn.button('reset');
                    swal("Error", "Server side error", "error");
                });
            } else if (action == 'sent') {
                var btn = $(el).parents('.product-box').find('.sent-btn');

                changeProductStat(product, 1, function(data) {
                    if (data.status == 'ok') {
                        btn.show();
                    }
                }, function(data) {
                    swal("Error", "Server side error", "error");
                });
            }

            if (action != 'delete') {
                $(el).iCheck('uncheck');
            }
        }
    });
});

$('#save-changes').click(function(e) {
    var btn = $(this);
    var products = [];

    $('input[type=checkbox]').each(function(i, el) {
        if (el.checked) {
            products.push($(el).parents('.product-box').attr('product-id'));
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
                swal("Error", 'error' in data ? data.error : 'Server side error', "error");
            }
        },
        error: function(data) {
            swal("Error", 'error' in data ? data.error : 'Server side error', "error");
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
        swal('Please select a board first', '', "warning");
        return;
    }

    $('input[type=checkbox]').each(function(i, el) {
        if (el.checked) {
            products.push($(el).parents('.product-box').attr('product-id'));
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
                swal("Error", 'error' in data ? data.error : 'Server error', "error");
            }
        },
        error: function(data) {
            swal("Error", 'error' in data ? data.error : 'Server error', "error");
        },
        complete: function() {
            btn.button('reset');
        }
    });
});

function changeBoard(board_id, options) {
    // options.$trigger.button('loading');
    $.ajax({
        url: '/api/product-board',
        type: 'POST',
        data: {
            'product': options.$trigger.attr("product-id"),
            'board': board_id
        },
        success: function(data) {
            // options.$trigger.button('reset');

            if ('status' in data && data.status == 'ok') {
                if ('board' in data) {
                    options.$trigger.text('Board: ' + data.board.title);
                } else {
                    options.$trigger.text('Board');
                }
            } else {
                swal("Error", 'error' in data ? data.error : 'Server side error', "error");
            }
        },
        error: function(data) {
            options.$trigger.button('reset');
            swal("Error", 'error' in data ? data.error : 'Server side error', "error");
        },
        complete: function() {
            // options.$trigger.button('reset');
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
                        btn.parents('.col-md-3').remove();
                        swal("Deleted!", "The product has been deleted.", "success");
                    },
                    error: function(data) {
                        swal("Error", "Server side error", "error");
                    }
                });
            }
        });
});

$('#shopify-send-btn').click(function(e) {

    $(this).button('loading');

    var products = [];
    var products_ids = [];

    $('#modal-shopify-send .progress').show();

    $('input[type=checkbox]').each(function(i, el) {
        if (el.checked) {
            products.push({
                product: $(el).parents('.product-box').attr('product-id'),
                element: $(el).parents('.product-box')
            });

            products_ids.push($(el).parents('.product-box').attr('product-id'));
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

                        callback_data.element.find('input[type=checkbox]').iCheck('uncheck');

                        var btn = callback_data.element.find('.sent-btn');
                        changeProductStat(callback_data.product, 1, function(data) {
                            if (data.status == 'ok') {
                                btn.show();
                            }
                        }, function(data) {
                            console.log("Set as sent error", "Server side error");
                        });

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


function setupContextMenus() {
    $.contextMenu({
        selector: '.board-btn',
        trigger: 'left',
        callback: function(key, options) {
            if (key == 'add') {
                window.onBoardAdd = function(board) {
                    // options.$trigger.text('Board: '+board.title);
                    boardsMenu['' + board.id] = {
                        name: board.title
                    };
                    changeBoard(board.id, options);

                    $.contextMenu('destroy');
                    setupContextMenus();
                };

                $('#modal-board-add').modal('show');
            } else if (key == 'clear') {
                changeBoard(0, options);
            } else {
                changeBoard(key, options);
            }
        },
        items: boardsMenu
    });
}

$('.filter-btn').click(function(e) {
    $('#modal-filter').modal('show');
});

$("#product-filter-form").submit(function() {
    $(this).find(":input").filter(function() {
        return !this.value;
    }).attr("disabled", "disabled");
    return true; // ensure form still submits
});


$(function() {
    setupContextMenus();

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
