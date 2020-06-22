(function() {
    'use strict';

    $("#id_date").datepicker();

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
