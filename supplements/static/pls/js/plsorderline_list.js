(function() {
    'use strict';

    $('#label-warning-modal').on('hide.bs.modal', function() {
        $('#label-warning-modal .download_latest_label').addClass('hidden');
        $('#label-warning-modal .newer_available').addClass('hidden');
        $('#label-warning-modal .current_is_rejected').addClass('hidden');
    });

    $('a.download-order-item-label').on('click', function(e) {
        e.preventDefault();
        var itemID = $(this).data('item-id');
        $.ajax({
            url: api_url('order-line-info', 'supplements'),
            type: 'GET',
            context: this,
            data: {item_id: itemID},
            success: function(r) {
                if (r.status == 'ok') {
                    var newVersionApproved = r.newer_available && r.latest_is_approved;
                    if (r.current_is_rejected || newVersionApproved) {
                        showWarnings(r);
                    } else {
                        markLabelAsPrinted.call(this);
                        window.open(r.label_url, '_blank');
                    }
                }
            },
            error: function (data) {
                displayAjaxError('Download Error', 'Please try again later!');
            },
        });
    });

    $('.sync-shipstation').on('click', function(e) {
        e.preventDefault();
        var orderID = $(this).data('order-id');

        var shipstationUrl = 'https://ssapi11.shipstation.com/shipments?storeID=171654&includeShipmentItems=False';
        $.ajax({
            url: '/supplements/shipstation/webhook/order_shipped',
            type: 'POST',
            context: $(this),
            contentType: 'application/json',
            data: JSON.stringify({
                "resource_type": "SHIP_NOTIFY",
                "resource_url": shipstationUrl + '&orderId=' + orderID
            }),
            beforeSend: function() {
                $(this).button('loading');
            },
            error: function (data) {
                displayAjaxError('Shipstation Sync', data);
            },
            complete: function() {
                $(this).button('reset');
            }
        });
    });

    function showWarnings(r) {
        // Shows the modal
        $('#label-warning-modal').modal('show');

        // Updates the label download button with label data
        $('#download-label').prop('href', r.label_url);
        $('#download-label').attr('data-item-id', r.item_id);

        if (r.current_is_rejected) {
            // Warns that current label is rejected
            $('#label-warning-modal .current_is_rejected').removeClass('hidden');
        }

        // If a newer label is available
        if (r.newer_available) {
            if (r.latest_is_approved) {
                // Warns that a newer label is available
                $('#label-warning-modal .newer_available').removeClass('hidden');
                // Updates the latest label download button with label data
                $('#download-latest-label').prop('href', r.latest_label_url);
                $('#download-latest-label').attr('data-item-id', r.item_id);
                // Shows the button to download new, approved label
                $('#label-warning-modal .download_latest_label').removeClass('hidden');
            }
        }
    }
})();
