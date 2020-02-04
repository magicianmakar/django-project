var itemsReadyForPrint = {};
var totalCostItemsPrint = 0.0;

/* Initialize orders */
function orderPrints(current_order, exclude_lines) {
    exclude_lines = typeof(exclude_lines) !== 'undefined' ? exclude_lines : false;

    var order = {
        items: []
    };

    $('.line[supplier-type="dropified-print"]', current_order).each(function(i, el) {
        if (exclude_lines) {
            // Check if we should exclude this line if "exclude" attribute is "true"
            if ($(el).attr('exclude') === 'true') {
                return;
            }
        }

        if ($(el).hasClass('bundled')) {
            var bundleBtn = $('.order-bundle', el);
            if (bundleBtn.attr('supplier-type') == 'dropified-print') {
                var order_data_id = bundleBtn.attr('order-data');
                var order_name = bundleBtn.attr('order-number');
                var store_type = bundleBtn.attr('store-type');

                // TODO
                /*orderBundle(order_data_id, order_name, store_type, function(data) {
                    toastr.error(data, 'Order Bundle');
                });*/
            }
        } else {
            if ($(el).attr('line-data') && !$(el).attr('line-track')) {
                order.items.push({
                    order_data: $(el).attr('order-data-id'),
                    order_name: $(el).attr('order-number'),
                    order_id: $(el).attr('order-id'),
                    line_id: $(el).attr('line-id'),
                    line_title: $(el).attr('line-title'),
                    item_price: '-',
                    order_status: 'Pending'
                });
            }
        }
    });

    if (order.items.length) {
        order.order_name = order.items[0].order_name;
        order.line_id = $.map(order.items, function(el) {
            return el.line_id;
        });
        order.line_title = '<ul style="padding:0px;overflow-x:hidden;">';
        order.line_title += $.map(order.items.slice(0, 3), function(el) {
            return '<li>&bull; ' + el.line_title +'</li>';
        }).join('');
        if (order.items.length > 3) {
            var extra_count = order.items.length - 3;
            order.line_title += '<li>&bull; Plus ' + (extra_count) +' Product' + (extra_count > 1 ? 's' : '') + '...</li>';
        }
        order.line_title += '</ul>';

        addOrdersToPrint([order]);
    } else {
        toastr.error('The items have been ordered or are not connected', 'No items to order');
    }
}


$('.order-prints').on('click', function(e) {
    var order = $(this).parents('.order');
    orderPrints(order);
});

$('.order-seleted-prints').click(function (e) {
    e.preventDefault();

    var order = $(this).parents('.order');
    var selected = 0;

    order.find('.line-checkbox').each(function (i, el) {
        if(!el.checked) {
            $(el).parents('.line').attr('exclude', 'true');
        } else {
            selected += 1;
            $(el).parents('.line').attr('exclude', 'false');
        }
    });

    orderPrints(order, true);
});

function initProgress(itemsLength, message) {
    $('#print-process').text(message);
    $('#print-progress').attr('orders-count', itemsLength).show();
    $('#print-progress').attr('orders-success', '0');
    $('#print-progress').attr('orders-error', '0');
    $('.print-place-order-btn').attr('disabled', true);
    $('.progress-bar-success').css('width', '0%').text('');
    $('.progress-bar-danger').css('width', '0%').text('');
}

function updateProgress(success) {
    var ordersCount = parseInt($('#print-progress').attr('orders-count'));
    var ordersSuccess = parseInt($('#print-progress').attr('orders-success'));
    var ordersError = parseInt($('#print-progress').attr('orders-error'));
    if (success) {
        ordersSuccess += 1;
    } else {
        ordersError += 1;
    }
    $('#print-progress').attr('orders-success', ordersSuccess);
    $('#print-progress').attr('orders-error', ordersError);

    if (ordersCount == (ordersSuccess + ordersError)) {
        $('#print-progress .fa-spin').removeClass('fa-spin');
        $('#print-progress .progress').removeClass('active');
        $('#print-process').text('Done');
    }

    $('.progress-bar-success').css('width', ((ordersSuccess * 100.0) / ordersCount) + '%')
        .text(ordersSuccess + ' item' + (ordersSuccess > 1 ? 's' : ''));

    $('.progress-bar-danger').css('width', ((ordersError * 100.0) / ordersCount) + '%')
        .text(ordersError + ' item' + (ordersError > 1 ? 's' : ''));
}

function addOrderToList(orderDataID, orderInfo) {
    var tr = $('#print-' + orderDataID);
    if (tr.length === 0) {
        tr = $('<tr id="print-' + orderDataID + '">');
        $('#modal-place-orders-dropified-print .table tbody').append(tr);
    }

    var orderTemplate = Handlebars.compile($("#dropified-print-order-template").html());
    tr.html(orderTemplate({'order': orderInfo}));
}

/* Add order to "queue" */
function getOrderData(orderInfo) {
    return $.ajax({
        url: api_url('order-data', window.storeType),
        type: 'GET',
        data: {
            order: orderInfo.order_data,
        }
    }).then(function(orderData) {
        return $.ajax({
            url: api_url('placed-item', 'prints'),
            type: 'POST',
            data: JSON.stringify({
                order_data_id: orderData.id,
                source_id: orderData.source_id,
                variant: orderData.variant,
                store_type: window.storeType,
                store: orderData.store
            })
        }).then(function(itemData) {
            var variantTitle = $.map(orderData.variant, function(v) { return v.title || v; }).join(' / ');
            var itemPrice = parseFloat(itemData.price) * orderData.quantity;
            orderData.print_order_info = {
                'order_status': 'Ready to order',
                'order_name': orderInfo.order_name,
                'line_title': orderInfo.line_title + ' - ' + variantTitle,
                'line_quantity': orderData.quantity,
                'item_price': '$' + itemPrice.toFixed(2),
                'from': itemData.from
            };

            var orderKey = orderInfo.order_data.replace(/_[^_]+$/, '');
            if (!itemsReadyForPrint[orderKey]) {
                itemsReadyForPrint[orderKey] = [];
            }
            itemsReadyForPrint[orderKey].push(orderData);
            totalCostItemsPrint += itemPrice;

            addOrderToList(orderInfo.order_data, orderData.print_order_info);
            updateProgress(true);
        });
    }).fail(function(data) {
        addOrderToList(orderInfo.order_data, {
            'error': getAjaxError(data),
            'order_name': orderInfo.order_name,
            'line_title': orderInfo.line_title,
            'item_price': '-'
        });
        updateProgress();
    });
}

function addOrdersToPrint(orders) {
    itemsReadyForPrint = {};
    totalCostItemsPrint = 0.0;

    console.log(orders);
    $('#prints-total-cost').text('-');
    $('#modal-place-orders-dropified-print .table tbody > *').remove();
    var itemsLength = $.map(orders, function(order) {
        if (!order.items) return 1;  // For single item orders
        return order.items.length;
    }).reduce(function(total, len) { return total + len; });
    initProgress(itemsLength, 'Fetching data for Print On Demand items...');

    var printItems = [];
    for (var i = 0; i < orders.length; i++) {
        if (orders[i].items) {
            for (var j = 0, jLength = orders[i].items.length; j < jLength; j++) {
                addOrderToList(orders[i].items[j].order_data, orders[i].items[j]);
                printItems.push(orders[i].items[j]);
            }
        } else {  // Orders with single item
            orders[i].order_status = 'Pending';
            addOrderToList(orders[i].order_data, orders[i]);
            printItems.push(orders[i]);
        }
    }
    $('#modal-place-orders-dropified-print').modal('show');
    $('.print-place-order-btn').removeClass('hidden');

    P.map(printItems, getOrderData).finally(function() {
        if (!$.isEmptyObject(itemsReadyForPrint)) {
            $('.print-place-order-btn').attr('disabled', false);
        }
        $('#prints-total-cost').text('$' + totalCostItemsPrint.toFixed(2));
    });
}

/* Place and fulfill orders */
function fulfillOrder(order, onSuccess) {
    return $.ajax({
        url: api_url('order-fulfill', window.storeType),
        type: 'POST',
        data: {
            'order_id': order.order_id,
            'line_id': order.line_id,
            'store': order.store,
            'aliexpress_order_id': order.source_id,
            'combined': order.combined ? 1 : null,
            'source_type': order.source_type,
        }
    }).then(onSuccess);
}

$('.print-place-order-btn').on('click',  function() {
    var itemsLength = $.map(itemsReadyForPrint, function(items) { return items.length; }).reduce(function(total, len) { return total + len; });
    initProgress(itemsLength, 'Placing orders in Dropified Print service...');

    P.map(Object.keys(itemsReadyForPrint), function(order_data) {
        return $.ajax({
            url: api_url('place-order', 'prints') + '?' + $.param({'store_type': window.storeType}),
            type: 'POST',
            data: JSON.stringify({orders: itemsReadyForPrint[order_data]}),
            context: {order_data: order_data},
            contentType: 'applicaton/json'
        }).then(function(data) {
            $.each(data.orders, function(k, order) {
                addOrderToList(order.order_data, order);
                updateProgress(order.success);
            });

            if (!data.fulfilled_order) {
                return;
            }

            // Fulfill using same ajax as extension
            return fulfillOrder(data.fulfilled_order, function(fulfillmentData) {
                if (fulfillmentData.status == 'ok') {
                    connectDropifiedPrintOrder(data.fulfilled_order.source_id);
                }
            });
        }).fail(function(data) {
            var ajaxError = getAjaxError(data);

            $.each(itemsReadyForPrint[order_data], function(k, order) {
                var orderResult = $.extend({}, order.print_order_info);
                orderResult.error = ajaxError;
                addOrderToList(order.id, orderResult);

                updateProgress();
            });
        });
    }).finally(function() {
        $('.print-place-order-btn').attr('disabled', false).addClass('hidden');
        $('#modal-place-orders-dropified-print .close-modal').removeClass('hidden');
    });
});
