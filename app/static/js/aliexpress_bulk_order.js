$(".place-aliexpress-orders").on("click", sendAliExpressOrders);
function sendAliExpressOrders(e) {
    var btn = $(this);
    btn.button('loading');
    var orderDataIDs = window.bulkOrderQueue;
    var order_ids = [];
    if (orderDataIDs.hasOwnProperty('data')) {
        if (Array.isArray(orderDataIDs.data)) {
            var orders = orderDataIDs.data;
            orders.forEach(function(item) {
                if (Array.isArray(item.items)) {
                    var temp = item.items;
                    temp.forEach(function(i) {
                        if (i.hasOwnProperty("order_data")) {
                            var order_data = i.order_data.split("_");
                            order_data = order_data.slice(0, -1);
                            order_data = order_data.join("_");
                            order_ids.push(order_data);
                        }
                    });
                }    
           });
        }
    }

    var final_ids = order_ids.filter(onlyUnique);
    final_ids.reverse();
    placeBulkApiOrder(btn, final_ids);
}

function onlyUnique(value, index, self) {
    return self.indexOf(value) === index;
}

function placeBulkApiOrder(btn, final_ids) {
    final_ids = final_ids;
    var order_data = final_ids.pop().split('_');  // split order data which contains store, order, line id
    var elem = '#status-' + order_data[1];
    
    $.ajax({
        url: '/api/order-place',
        type: 'POST',
        data: {
            'store': order_data[0], // store id
            'order_id': order_data[1], // order id
        },
        beforeSend: function() {
            $(elem).text("Processing...").removeClass("text-danger").addClass("text-success");
        },
    }).done(function(data) {
        $(elem).text("Order Placed").removeClass("text-danger").addClass("text-primary");
        if (!final_ids.length) {
            btn.button('reset');
            swal.close();
            toastr.success('All items ordered', 'Order Placed');
            $("#modal-quick-aliexpress-order").modal('hide');
        }
        else {
            placeBulkApiOrder(btn, final_ids);
        }

    }).fail(function(data) {
        $(elem).text("Order Processing failed.").removeClass("text-success").addClass("text-danger");
        displayAjaxError('Place Order', data);
        btn.button('reset');
    }).always(function() {
        // btn.button('reset');
    });
}