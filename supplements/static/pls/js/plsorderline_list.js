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
                        $(e.target).closest('tr').find('.label-status').find('.label').hide();
                        $(e.target).closest('tr').find('.label-status').append('<span class="label label-primary">Printed</span>');
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
                "resource_url": shipstationUrl + '&orderNumber=' + orderID
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

    $('.fix-barcode').on('click', function(e) {
        e.preventDefault();

        $.ajax({
            url: $(this).attr('href'),
            context: $(this),
            success: function(data) {
                $('#modal-new-label-barcode .modal-body').empty().append(
                    $('<embed class="img-fluid" src="' + data.url + '" type="application/pdf" height="500px" width="100%">')
                );
                var renewURL = $(this).attr('href').split('?')[0] + '?renew=' + data.url;
                $('#modal-new-label-barcode .renew').attr('href', renewURL);
                $('#modal-new-label-barcode').modal('show');
            },
            error: function(data) {
                displayAjaxError('Fix Barcode', data);
            },
        });
    });
    $('#modal-new-label-barcode .renew').on('click', function() {
        $('#modal-new-label-barcode').modal('hide');
    });

    $('#modal-label-history').on('show.bs.modal', function(e) {
        $(this).find('.modal-body').html($(e.relatedTarget).siblings('.history').html());
    });
})();
