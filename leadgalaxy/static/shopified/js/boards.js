/* global $, toastr, swal, displayAjaxError, sendProductToShopify */
/* global boardsMenu */

(function() {
'use strict';

var currentBoardBox = null;

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
                displayAjaxError('Board Product', data);
            }
        },
        error: function(data) {
            displayAjaxError('Board Product', data);
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
        swal({
            title: "Delete Products",
            text: "Are you sure that you want to permanently delete the selected products?",
            type: "warning",
            showCancelButton: true,
            closeOnCancel: true,
            closeOnConfirm: true,
            confirmButtonColor: "#DD6B55",
            confirmButtonText: "Delete Permanently",
            cancelButtonText: "Cancel"
        },
        function(isConfirmed) {

            if (isConfirmed) {
                    boardBox.find('input.item-select[type=checkbox]').each(function(i, el) {
                    if (el.checked) {
                        var product = $(el).parents('.product-box').attr('product-id');
                        if (action == 'delete') {
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
                                    displayAjaxError('Delete Product', data);
                                }
                            });
                        }

                        $(el).iCheck('uncheck');
                    }
                });
            }
        });
    } else if (action == 'edit') {
        $('#modal-products-edit-form').modal('show');
        return;
    } else if (action == 'shopify-send') {
        currentBoardBox = boardBox;
        $('#modal-shopify-send').modal({backdrop: 'static', keyboard: false});
        return;
    } else if (action == 'board-remove') {
        var btn = $(this);
        var products = [];
        var products_el = [];
        var board_id = boardBox.attr('board-id');

        boardBox.find('input.item-select[type=checkbox]').each(function(i, el) {
            if (el.checked) {
                products.push($(el).parents('.product-box').attr('product-id'));
                products_el.push($(el));
                $(el).iCheck('uncheck');
            }
        });

        deletFromBoard(board_id, products, products_el);
    }

    boardBox.find('.selected-actions').val('');
});

$('#modal-products-edit-form #save-changes').click(function(e) {
    var btn = $(this);
    var products = [];

    $('input.item-select[type=checkbox]').each(function(i, el) {
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
                displayAjaxError('Edit Products', data);
            }
        },
        error: function(data) {
            displayAjaxError('Edit Products', data);
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

    swal({
        title: "Empty Board",
        text: "This will empty the board from it's products. \n" +
              "The products are not delete from your account. \n" +
              "Are you sure you want to empty the board?",
        type: "warning",
        showCancelButton: true,
        closeOnCancel: true,
        closeOnConfirm: false,
        confirmButtonColor: "#DD6B55",
        confirmButtonText: "Empty Board",
        cancelButtonText: "Cancel"
    },
    function(isConfirmed) {
        $.ajax({
            url: '/api/board-empty',
            type: 'POST',
            data: {
                board: board
            },
            success: function(data) {
                if ('status' in data && data.status == 'ok') {
                    swal.close();
                    toastr.success("The board is now empty.", "Empty Board");

                    $(btn.parents('.board-box').find('.ibox-content')[0]).html(
                        '<h3 class="text-center">No product in this board.</h3>'
                    );

                    btn.parents('.board-box').find('.products-count').text('0');
                } else {
                    displayAjaxError('Empty Board', data);
                }
            },
            error: function(data) {
                displayAjaxError('Empty Board', data);
            },
            complete: function() {}
        });
    });
});

$('.board-delete').click(function(e) {
    e.preventDefault();
    var board = $(this).attr('board-id');
    var btn = $(this);

    swal({
        title: "Delete Board",
        text: "This will delete the board permanently. Are you sure you want to delete it?",
        type: "warning",
        showCancelButton: true,
        closeOnCancel: true,
        closeOnConfirm: false,
        confirmButtonColor: "#DD6B55",
        confirmButtonText: "Delete Permanently",
        cancelButtonText: "Cancel"
    },
    function(isConfirmed) {
        if (isConfirmed) {
            $.ajax({
                url: '/api/board-delete',
                type: 'POST',
                data: {
                    board: board
                },
                success: function(data) {
                    if ('status' in data && data.status == 'ok') {
                        btn.parents('.board-box').remove();
                        swal.close();
                        toastr.success('Board has been deleted.', 'Delete Board');
                    } else {
                        displayAjaxError('Delete Board', data);
                    }
                },
                error: function(data) {
                    displayAjaxError('Delete Board', data);
                },
                complete: function() {}
            });
        }
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
    var btn = $(this);
    btn.button('loading');

    var products = [];
    var products_ids = [];

    $('#modal-shopify-send .progress').show();
    $('#modal-shopify-send input, #modal-shopify-send select').prop('disabled', true);

    $('input.item-select[type=checkbox]', currentBoardBox).each(function(i, el) {
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
        btn.button('reset');
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
                            callback_data.element.find('input.item-select[type=checkbox]').iCheck('uncheck');

                            total_sent_success += 1;
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

$("#product-filter-form").submit(function() {
    $(this).find(":input").filter(function() {
        return !this.value;
    }).attr("disabled", "disabled");
    return true; // ensure form still submits
});

})();
