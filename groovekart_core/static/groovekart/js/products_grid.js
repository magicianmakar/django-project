/* global $, toastr, swal, displayAjaxError, sendProductToGrooveKart */
/* global boardsMenu */

(function(boardsMenu) {
'use strict';

var selectedProducts = 0;
var createdParents = 0;

$('.bulk-action').on('click', function(e) {
    e.preventDefault();
    var action = $(this).attr('data-bulk-action');

    if (!$('input.item-select[type=checkbox]').is(':checked')) {
        if ($(this).hasClass('not-connected')) {
            window.location.href = $(this).attr('href');
            return;
        }
        swal('Please select a product first', '', "warning");
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
                    $('input.item-select[type=checkbox]').each(function(i, el) {
                        if (el.checked) {
                            var product = $(el).parents('.product-box').attr('product-id');
                            $.ajax({
                                url: api_url('product', 'gkart') + '?' + $.param({product: product}),
                                type: 'DELETE',
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
        $('#modal-products-edit-form').modal('show');
        return;
    } else if (action == 'board') {
        $('#modal-board-product').modal('show');
        return;
    } else if (action == 'groovekart-send') {
        $('#modal-groovekart-send').modal('show');
        return;
    } else if (action === 'create-parent') {
        $('button.dropdown-toggle').button('loading');
        var products = $('input.item-select[type=checkbox]:checked');
        selectedProducts = products.length;
        products.each(function (i, el) {
            var product = $(el).parents('.product-box').attr('product-id');
            $.ajax({
                url: api_url('parent_product', 'multichannel'),
                type: 'POST',
                data: JSON.stringify({
                    product_id: product,
                    store_type: 'gkart'
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
        url: api_url('product-edit', 'gkart'),
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
        url: api_url('board-add-products', 'gkart'),
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
        url: api_url('product-board', 'gkart'),
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
                    url: api_url('product', 'gkart') + '?' + $.param({product: product}),
                    type: 'DELETE',
                    success: function(data) {
                        btn.parents('.col-md-3').remove();

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

$('#groovekart-send-btn').click(function(e) {
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

    $('#modal-groovekart-send').modal();

    var pusher = new Pusher(pusherKey, {encrypted: true});
    var channel = pusher.subscribe(pusherChannel);

    channel.bind('pusher:subscription_succeeded', function() {
        $.ajax({
            url: api_url('products-info', 'gkart'),
            type: 'GET',
            data: {products: productIds},
            success: function(data) {
                var i, len, productId;
                for (i = 0, len = productIds.length; i < len; i++) {
                    productId = productIds[i];
                    sendProductToGrooveKart(productId, storeId, publish);
                }
            }
        });
    });

    var totalSuccess = 0;
    var totalError = 0;

    channel.bind('product-export', function(data) {
        var productId = String(data.product);

        if ($.inArray(productId, productIds) >= 0) {
            $('#product_' + productId).iCheck('disable').prop('checked', false);

            if (data.success) {
                toastr.success('Product sent to Groovekart store.');
                totalSuccess += 1;
            } else {
                toastr.error(data.error);
                totalError += 1;
            }
        }

        if ((totalSuccess + totalError) === productIds.length) {
            $('#modal-groovekart-send').modal('hide');
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

                $('#modal-board-add').prop('store-type', 'gkart');
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


$('.groovekart-product-import-btn').click(function (e) {
    e.preventDefault();

    $('#modal-groovekart-product .groovekart-store').val($(this).attr('store'));
    $('#modal-groovekart-product').modal('show');
});

window.groovekartProductSelected = function (store, gkart_id) {
    $('#modal-groovekart-product').modal('hide');

    $('#modal-supplier-link').prop('groovekart-store', $('#modal-groovekart-product .groovekart-store').val());
    $('#modal-supplier-link').prop('groovekart-product', gkart_id);

    $('#modal-supplier-link').modal('show');
};

$('.product-original-link').bindWithDelay('keyup', function (e) {
    var input = $(e.target);
    var parent = input.parents('.product-export-form');
    var product_url = input.val().trim();

    if(!product_url.length || !(/aliexpress.com/i).test(product_url)) {
        return;
    }

    var product_id = product_url.match(/[\/_]([0-9]+)\.html/);
    if(product_id.length != 2) {
        return;
    } else {
        product_id = product_id[1];
    }

    $('.product-original-link-loading', parent).show();

    window.extensionSendMessage({
        subject: 'ProductStoreInfo',
        product: product_id,
    }, function(rep) {
        $('.product-original-link-loading', parent).hide();

        if (rep && rep.name) {
            $('.product-supplier-name', parent).val(rep.name);
            $('.product-supplier-link', parent).val(rep.url);
        }
    });
}, 200);

$('.add-supplier-info-btn').click(function (e) {
    e.preventDefault();

    $.ajax({
            url: api_url('import-product', 'gkart'),
            type: 'POST',
            data: {
                store: $('#modal-supplier-link').prop('groovekart-store'),
                supplier: $('.product-original-link').val(),
                vendor_name: $('.product-supplier-name').val(),
                vendor_url: $('.product-supplier-link').val(),
                product: $('#modal-supplier-link').prop('groovekart-product'),
            },
        }).done(function (data) {
            toastr.success('Product is imported!', 'Product Import');

            $('#modal-supplier-link').modal('hide');

            setTimeout(function() {
                window.location.href = '/gkart/product/' + data.product;
            }, 1500);
        }).fail(function(data) {
            displayAjaxError('Product Import', data);
        }).always(function() {
        });
});

$('#modal-supplier-link').on('hidden.bs.modal', function (e) {
    $(this).find('.product-export-form').find("input[type=text]").val("");
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
