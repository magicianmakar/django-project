/* global $, toastr, swal, displayAjaxError, sendProductToShopify */
/* global boardsMenu, sendProductToFB, api_url, Pusher */

(function(boardsMenu) {
'use strict';

var selectedProducts = 0;
var createdParents = 0;

$('.bulk-action').on('click', function(e) {
    var action = $(this).attr('data-bulk-action');


    if (action.length === 0) {
        swal('Please select an action first', '', "warning");
        return;
    }

    if (action === 'delete') {
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
                    $('input.item-select[type=checkbox]').each(function(i, el) {
                        if (el.checked) {
                            var node = $(el);
                            var productId = node.parents('.product-box').attr('product-id');
                            deleteProduct(productId, function() {
                                node.parents('.col-md-3').remove();
                            });
                            node.iCheck('uncheck');
                        }
                    });
                }
            });
    } else if (action === 'edit') {
        $('#modal-products-edit-form').modal('show');
        return;
    } else if (action === 'board') {
        $('#modal-board-product').modal('show');
        return;
    } else if (action === 'fb-send') {
        $('#modal-fb-send').modal('show');
        return;
    } else if (action === 'create-parent') {
        $('button.dropdown-toggle').button('loading');
        var products = $('input.item-select[type=checkbox]:checked');
        selectedProducts = products.length;
        products.each(function (i, el) {
            var product = $(el).parents('.product-box').attr('data-product-id');
            $.ajax({
                url: api_url('parent_product', 'multichannel'),
                type: 'POST',
                data: JSON.stringify({
                    product_id: product,
                    store_type: 'fb'
                }),
                contentType: "application/json; charset=utf-8",
                dataType: "json",
                success: function (data) {
                    if (data.status === 'ok') {
                        createdParents += 1;
                        if (selectedProducts === createdParents) {
                            $('button.dropdown-toggle').button('reset');
                            toastr.success('Parents for selected products were successfully created!', 'Parents Created');
                            selectedProducts = 0;
                            createdParents = 0;
                        }
                    } else {
                        $('button.dropdown-toggle').button('reset');
                        swal("Error", "Server Error", "error");
                    }
                },
                error: function (data) {
                    $('button.dropdown-toggle').button('reset');
                    swal("Error", "Server Error", "error");
                }
            });

            $(el).iCheck('uncheck');
        });
        return;
    }

    $('#selected-actions').val('');
    $('input.item-select[type=checkbox]').each(function(i, el) {
        if (el.checked) {
            var product = $(el).parents('.product-box').attr('product-id');

            if (action != 'delete') {
                $(el).iCheck('uncheck');
            }
        }
    });
});

function getSelectProduct() {
    var products = [];

    $('input.item-select[type=checkbox]').each(function(i, el) {
        if (el.checked) {
            products.push($(el).parents('.product-box').attr('product-id'));
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

    if ($('#product-tags').val().length) {
        data['tags'] = $('#product-tags').val();
    }

    if ($('#product-weight').val().length) {
        data['weight'] = $('#product-weight').val();
        data['weight_unit'] = $('#product-weight-unit').val();
    }

    btn.button('loading');

    $.ajax({
        url: api_url('product-edit', 'fb'),
        type: 'POST',
        data: data,
        success: function(data) {
            if ('status' in data && data.status == 'ok') {
                window.location.href = window.location.href;
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

$('#board-product-send').click(function(e) {
    var btn = $(this);
    var products = [];

    if ($('#selected-board').val().length === 0) {
        swal('Please select a board first', '', "warning");
        return;
    }

    $('input.item-select[type=checkbox]').each(function(i, el) {
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
        url: api_url('board-add-products', 'fb'),
        type: 'POST',
        data: data,
        success: function(data) {
            if ('status' in data && data.status == 'ok') {
                $('#modal-board-product').modal('hide');
                toastr.success('Added to board');
            } else {
                displayAjaxError('Add to board', data);
            }
        },
        error: function(data) {
            displayAjaxError('Add to board', data);
        },
        complete: function() {
            btn.button('reset');
        }
    });
});

function changeBoard(board_id, options) {
    // options.$trigger.button('loading');
    $.ajax({
        url: api_url('product-board', 'fb'),
        type: 'POST',
        data: {
            'product': options.$trigger.attr("product-id"),
            'board': board_id
        },
        success: function(data) {
            // options.$trigger.button('reset');

            if ('status' in data && data.status === 'ok') {
                if ('board' in data) {
                    options.$trigger.text('Board: ' + data.board.title);
                } else {
                    options.$trigger.text('Board');
                }
            } else {
                displayAjaxError('Board Products', data);
            }
        },
        error: function(data) {
            options.$trigger.button('reset');
            displayAjaxError('Board Products', data);
        },
        complete: function() {
            // options.$trigger.button('reset');
        }
    });
}

function deleteProduct(productGuid, callback) {
    $.ajax({
        url: api_url('product', 'fb') + '?' + $.param({product: productGuid}),
        type: 'DELETE',
        success: function(data) {
            var pusher = new Pusher(data.pusher.key);
            var channel = pusher.subscribe(data.pusher.channel);

            channel.bind('product-delete', function(eventData) {
                if (eventData.product === productGuid) {
                    pusher.unsubscribe(data.pusher.channel);

                    if (eventData.success && callback) {
                        callback();
                    }
                    if (eventData.error) {
                        displayAjaxError('Delete Product', data);
                    }
                }
            });
        },
        error: function(data) {
            displayAjaxError('Delete Product', data);
        }
    });
}


$('.delete-product-btn').click(function(e) {
    var btn = $(this);
    var productId = btn.attr('product-id');

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
                deleteProduct(productId, function() {
                    btn.parents('.col-md-3').remove();
                    swal.close();
                    toastr.success("The product has been deleted.", "Deleted!");
                });
            }
        });
});

$('#fb-send-btn').click(function(e) {
    var $btn = $(this).button('loading');
    var storeId = $('#send-select-store').val();
    var publish = $('#send-product-visible').prop('checked');
    var pusherChannel = $('#send-select-store option:selected').data('store-channel');
    var pusherKey = window.sub_conf.key;
    var productIds = [];

    // Fetches all product ID's of selected products
    $('input.item-select[type=checkbox]').each(function(i, el) {
        if (el.checked) {
            productIds.push($(el).parents('.product-box').attr('product-id'));
        }
    });

    if (productIds.length === 0) {
        swal('Please select a product(s) first', '', "warning");
        $btn.button('reset');
        return;
    }

    $('#modal-fb-send').modal();

    var pusher = new Pusher(pusherKey, {encrypted: true});
    var channel = pusher.subscribe(pusherChannel);

    channel.bind('pusher:subscription_succeeded', function() {
        productIds.forEach(function(productId) {
            sendProductToFB(productId, storeId, publish);
        });
    });

    var totalSuccess = 0;
    var totalError = 0;

    channel.bind('product-export', function(data) {
        var productId = String(data.product);

        if ($.inArray(productId, productIds) >= 0) {
            if (data.success) {
                toastr.success('Product sent to Facebook store.');
                totalSuccess += 1;
            } else if (data.error) {
                toastr.error(data.error);
                totalError += 1;
            }
        }

        if ((totalSuccess + totalError) === productIds.length) {
            $('#modal-fb-send').modal('hide');
            $btn.button('reset');
            pusher.unsubscribe(pusherChannel);
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

                $('#modal-board-add').prop('store-type', 'fb');
                $('#modal-board-add').modal('show');
            } else if (key == 'clear') {
                changeBoard(0, options);
            } else {
                changeBoard(key, options);
            }
        },
        items: boardsMenu,
        events: {
            show: function(opt) {
                setTimeout(function() {
                    opt.$menu.css({
                        'z-index': '10000',
                        'max-height': '300px',
                        'overflow': 'auto',
                    });
                }, 100);

                return true;
            }
        }
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


$('.fb-product-import-btn').click(function (e) {
    e.preventDefault();

    $('#modal-fb-product .fb-store').val($(this).attr('store'));
    $('#modal-fb-product').modal('show');
});

window.fbProductSelected = function (store, fbId) {
    $('#modal-fb-product').modal('hide');

    $('#modal-supplier-link').prop('fb-store', $('#modal-fb-product .fb-store').val());
    $('#modal-supplier-link').prop('fb-product', fbId);

    $('#modal-supplier-link').modal('show');
};

$('.product-original-link').bindWithDelay('keyup', function (e) {
    var input = $(e.target);
    var parent = input.parents('.product-export-form');
    var product_url = input.val().trim();

    renderSupplierInfo(product_url, parent);
}, 200);

$('.add-supplier-info-btn').click(function (e) {
    e.preventDefault();

    $.ajax({
            url: api_url('import-product', 'fb'),
            type: 'POST',
            data: {
                store: $('#modal-supplier-link').prop('fb-store'),
                supplier: $('.product-original-link').val(),
                vendor_name: $('.product-supplier-name').val(),
                vendor_url: $('.product-supplier-link').val(),
                product: $('#modal-supplier-link').prop('fb-product'),
            },
        }).done(function (data) {
            toastr.success('Product is imported!', 'Product Import');

            $('#modal-supplier-link').modal('hide');

            setTimeout(function() {
                window.location.href = '/fb/product/' + data.product;
            }, 1500);
        }).fail(function(data) {
            displayAjaxError('Product Import', data);
        }).always(function() {
        });
});

$(function() {
    setupContextMenus();
/*
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
*/
});
})(boardsMenu);
