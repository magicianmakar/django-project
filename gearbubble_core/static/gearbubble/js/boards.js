$(document).ready(function() {
    'use strict';

    $('.dataTables').on('draw.dt', function(e) {
        $('.dataTables tr').each(function(i, el) {
            var info = $(el).find('td');

            if (info.length == 1) {
                $(el).find('td').last().text('No board found.').addClass('text-center');
                return;
            }
        });
    });

    var table = $('.dataTables').dataTable({
        responsive: true,
        autoWidth: false,
        dom: 'T<"clear">lfrtip',
        bLengthChange: false,
        iDisplayLength: 25,
        tableTools: {
            aButtons: [],
        }
    });

    $('.gear-add-board-btn').click(function(e) {
        e.preventDefault();
        $('#gear-modal-board-add').modal('show');
    });

    $("#gear-new-board-add-form").submit(function(e) {
        e.preventDefault();
        var $title = $(this).find('input[name="title"]');
        var boardName = $title.val().trim();

        $.ajax({
            url: api_url('boards-add', 'gear'),
            type: 'POST',
            data: {title: boardName},
            success: function(data) {
                if ('status' in data && data.status == 'ok') {
                    $('#gear-modal-board-add').modal('hide');
                    $title.val('');

                    if (typeof(window.onBoardAdd) == 'function') {
                        window.onBoardAdd(data.board);
                    } else {
                        window.location.href = window.location.href;
                    }
                } else {
                    displayAjaxError('Create Board', data);
                }
            },
            error: function (data) {
                displayAjaxError('Create Board', data);
            }
        });
    });

    $('.gear-edit-board-btn').click(function(e) {
        e.preventDefault();
        var boardId = $(this).data('board-id');

        $.get(api_url('board-config', 'gear'), {'board_id': boardId}).done(function(data) {
            var $form = $('#gear-board-update-form');
            $form.find('input[name="board-id"]').val(boardId);
            $form.find('input[name="title"]').val(data.title);
            $form.find('input[name="product-title"]').val(data.config.title);
            $form.find('input[name="product-tags"]').val(data.config.tags);
            $form.find('input[name="product-type"]').val(data.config.type);
            $('#gear-modal-board-update').modal('show');
        });
    });

    $('#gear-board-update-form').submit(function(e) {
        e.preventDefault();
        var data = {
            board_id: $(this).find('input[name="board-id"]').val().trim(),
            title: $(this).find('input[name="title"]').val().trim(),
            product_title: $(this).find('input[name="product-title"]').val().trim(),
            product_tags: $(this).find('input[name="product-tags"]').val().trim(),
            product_type: $(this).find('input[name="product-type"]').val().trim()
        };

        $.post(api_url('board-config', 'gear'), data)
        .done(function() {
            $('#gear-modal-board-update').modal('hide');
            window.location.href = window.location.href;
        })
        .fail(function (data) {
            displayAjaxError('Update Board', data);
        });
    });

    $('.gear-delete-board-btn').click(function(e) {
        e.preventDefault();
        var boardId = $(this).data('board-id');

        swal({
            title: 'Are you sure?',
            text: 'Please, confirm if you want to delete this board.',
            type: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#DD6B55',
            confirmButtonText: 'Yes, delete it!',
            closeOnConfirm: false
        }, function() {
            $.ajax({
                url: api_url('board', 'gear') + '?' + $.param({board_id: boardId}),
                method: 'DELETE',
                success: function(data) {
                    if ('status' in data && data.status == 'ok') {
                        swal.close();
                        toastr.success('Board has been deleted.', 'Delete Board');
                        var selector = '#board-row-' + boardId;
                        var $row = $(selector);
                        if ($row.length) {
                            table.api().rows(selector).remove().draw();
                        } else {
                            window.location.href = '/gear/boards/list';
                        }
                    } else {
                        displayAjaxError('Delete Board', data);
                    }
                },
                error: function (data) {
                    displayAjaxError('Delete Board', data);
                }
            });
        });
    });

    $('.gear-empty-board-btn').click(function(e) {
        e.preventDefault();
        var boardId = $(this).data('board-id');

        swal({
            title: "Empty Board",
            text: "This will empty the board from its products. \n" +
                  "The products are not deleted from your account. \n" +
                  "Are you sure you want to empty the board?",
            type: "warning",
            showCancelButton: true,
            confirmButtonColor: "#DD6B55",
            confirmButtonText: "Empty Board",
            closeOnConfirm: false
        }, function(isConfirmed) {
            if (!isConfirmed) {
                return;
            }

            $.ajax({
                url: api_url('board-empty', 'gear'),
                data: {board_id: boardId},
                method: 'POST',
                success: function(data) {
                    if ('status' in data && data.status == 'ok') {
                        swal.close();
                        toastr.success("The board is now empty.", "Empty Board");
                        var selector = '#board-row-' + boardId;
                        var $row = $(selector);
                        if ($row.length) {
                            $row.find('.product-count').html('0');
                        } else {
                            window.location.href = window.location.href;
                        }
                    } else {
                        displayAjaxError('Empty Board', data);
                    }
                },
                error: function (data) {
                    displayAjaxError('Empty Board', data);
                }
            });
        });
    });

    var currentBoardBox = null;

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
                                    url: api_url('product', 'gear') + '?' + $.param({product: product}),
                                    type: 'DELETE',
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
        } else if (action == 'gearbubble-send') {
            currentBoardBox = boardBox;
            $('#modal-gearbubble-send').modal('show');
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

            if (!products.length) {
                toastr.warning("No Products selected.");
                return;
            }
            var param = {products: products, board_id: board_id};

            $.ajax({
                url: api_url('board-products', 'gear') + '?' + $.param(param),
                type: 'DELETE',
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

        if ($('#product-tags').val().length) {
            data['tags'] = $('#product-tags').val();
        }

        if ($('#product-weight').val().length) {
            data['weight'] = $('#product-weight').val();
            data['weight_unit'] = $('#product-weight-unit').val();
        }

        btn.button('loading');

        $.ajax({
            url: api_url('product-edit', 'gear'),
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

    $('#gearbubble-send-btn').click(function(e) {
        var $btn = $(this).button('loading');
        var storeId = $('#send-select-store').val();
        var publish = $('#send-product-visible').prop('checked');
        var pusherChannel = $('#send-select-store option:selected').data('store-channel');
        var pusherKey = window.PUSHER_KEY;
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

        $('#modal-gearbubble-send').modal();

        var pusher = new Pusher(pusherKey, {encrypted: true});
        var channel = pusher.subscribe(pusherChannel);

        channel.bind('pusher:subscription_succeeded', function() {
            $.ajax({
                url: api_url('products-info', 'gear'),
                type: 'GET',
                data: {products: productIds},
                success: function(data) {
                    var i, len, productId;
                    for (i = 0, len = productIds.length; i < len; i++) {
                        productId = productIds[i];
                        sendProductToGearBubble(productId, storeId, publish);
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
                    toastr.success('Product sent to GearBubble store.');
                    totalSuccess += 1;
                } else {
                    toastr.error(data.error);
                    totalError += 1;
                }
            }

            if ((totalSuccess + totalError) === productIds.length) {
                $('#modal-gearbubble-send').modal('hide');
                $btn.button('reset');
                pusher.unsubscribe(pusherChannel);
            }
        });
    });

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
                    url: api_url('product', 'gear') + '?' + $.param({product: product}),
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
});
