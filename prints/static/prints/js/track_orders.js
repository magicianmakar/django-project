function connectDropifiedPrintOrder(order_name) {
    $.ajax({
        url: api_url('sync-order', 'prints'),
        type: 'POST',
        data: {
            'store_type': window.storeType,
            'source_id': order_name,
            'connect': true
        }
    });
}

function checkDropifiedPrintOrder(order) {
    return $.ajax({
        url: api_url('sync-order', 'prints'),
        type: 'POST',
        data: {
            'store_type': window.storeType,
            'source_id': order.source_id
        }
    });
}
