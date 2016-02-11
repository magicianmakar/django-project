/* global $, toastr, swal, displayAjaxError, sendProductToShopify */
/* global boardsMenu */

(function(config, product) {
'use strict';

var currentBoardBox = null;

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
                    alert(data.error);
                    btn.button('reset');
                } else {
                    btn.hide();
                }
            },
            function(data) {
                btn.button('reset');
                alert('Server side error');
            });
    });

function deletFromBoard(board_id, products, products_el) {
    $.ajax({
        url: '/api/product-remove-board',
        type: 'POST',
        data: {
            products: products,
            board: board_id
        },
        success: function(data) {
            if ('status' in data && data.status == 'ok') {
                $.each(products_el, function(j, elc) {
                    elc.parents('.col-md-3').remove();
                });
            } else {
                alert('Server side error');
            }
        },
        error: function(data) {
            alert('Server side error');
        }
    });
}

$('.delete-from-board-btn').click(function(e) {
    var products = [$(this).attr('product-id')];
    var products_el = [$(this)];
    var board_id = $(this).parents('.board-box').attr('board-id');

    deletFromBoard(board_id, products, products_el);
});

$('.apply-btn').click(function(e) {
    var boardBox = $(this).parents('.board-box');

    var action = boardBox.find('.selected-actions').val();
    if (action == 'delete') {
        if (!confirm('Are you sure that you want to permanently delete the selected products?')) {
            return;
        }
    } else if (action == 'edit') {
        $('#modal-form').modal('show');
        return;
    } else if (action == 'shopify-send') {
        currentBoardBox = boardBox;
        $('#modal-shopify-send').modal('show');
        return;
    } else if (action == 'board-remove') {
        var btn = $(this);
        var products = [];
        var products_el = [];
        var board_id = boardBox.attr('board-id');

        boardBox.find('input[type=checkbox]').each(function(i, el) {
            if (el.checked) {
                products.push($(el).parents('.product-box').attr('product-id'));
                products_el.push($(el));
                $(el).iCheck('uncheck');
            }
        });

        deletFromBoard(board_id, products, products_el);
    }

    boardBox.find('.selected-actions').val('');
    boardBox.find('input[type=checkbox]').each(function(i, el) {
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
                    alert('Server side error');
                });
            } else if (action == 'sent') {
                var btn = $(el).parents('.product-box').find('.sent-btn');

                changeProductStat(product, 1, function(data) {
                    if (data.status == 'ok') {
                        btn.show();
                    }
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
                        $(el).parents('.col-md-3').remove();
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

$('.board-empty').click(function(e) {
    e.preventDefault();
    var board = $(this).attr('board-id');
    var btn = $(this);

    $.ajax({
        url: '/api/board-empty',
        type: 'POST',
        data: {
            board: board
        },
        success: function(data) {
            if ('status' in data && data.status == 'ok') {
                $(btn.parents('.board-box').find('.ibox-content')[0]).html(
                    '<h3 class="text-center">No product in this board.</h3>'
                );
            } else {
                alert('error' in data ? data.error : 'Server error');
            }
        },
        error: function(data) {
            alert('error' in data ? data.error : 'Server error');
        },
        complete: function() {}
    });
});

$('.board-delete').click(function(e) {
    e.preventDefault();
    var board = $(this).attr('board-id');
    var btn = $(this);

    $.ajax({
        url: '/api/board-delete',
        type: 'POST',
        data: {
            board: board
        },
        success: function(data) {
            if ('status' in data && data.status == 'ok') {
                btn.parents('.board-box').remove();
            } else {
                alert('error' in data ? data.error : 'Server error');
            }
        },
        error: function(data) {
            alert('error' in data ? data.error : 'Server error');
        },
        complete: function() {}
    });
});

$('.board-edit').click(function(e) {
    e.preventDefault();

    var board = $(this).attr('board-id');

    $.ajax({
        url: '/api/board-config',
        type: 'GET',
        data: {
            board: board,
        },
        success: function(data) {
            $('#smartboard-board').val(board);
            $('#board-title').val(data.title);
            $('#smartboard-product-title').val(data.config.title);
            $('#smartboard-product-type').val(data.config.type);
            $('#smartboard-product-tags').val(data.config.tags);

            $('#smartboard-modal').modal();
        }
    });
});

$('#smartboard-save-changes').click(function(e) {
    e.preventDefault();

    $.ajax({
        url: '/api/board-config',
        type: 'POST',
        data: {
            'store-title': $('#board-title').val(),
            'board': $('#smartboard-board').val(),
            'title': $('#smartboard-product-title').val(),
            'type': $('#smartboard-product-type').val(),
            'tags': $('#smartboard-product-tags').val(),
        },
        success: function(data) {
            $('#smartboard-modal').modal('hide');
            window.location = window.location;
        }
    });
});

$('#shopify-send-btn').click(function(e) {

    $(this).button('loading');

    var products = [];
    var products_ids = [];

    $('#modal-shopify-send .progress').show();

    $('input[type=checkbox]', currentBoardBox).each(function(i, el) {
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
})();
