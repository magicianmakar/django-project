(function() {
    'use strict';

    $("#id_date").datepicker();

    $('#label-warning-modal').on('hide.bs.modal', function() {
        $('#label-warning-modal .download_latest_label').addClass('hidden');
        $('#label-warning-modal .newer_available').addClass('hidden');
        $('#label-warning-modal .current_is_rejected').addClass('hidden');
        $('#label-warning-modal .current_not_approved').addClass('hidden');
        $('#label-warning-modal .latest_is_rejected').addClass('hidden');
        $('#label-warning-modal .latest_not_approved').addClass('hidden');
    });

    $('a.download-order-item-label').on('click', function(e) {
        e.preventDefault();
        var itemID = $(this).data('item-id');
        $.ajax({
            url: api_url('order-line-info', 'supplements'),
            type: 'GET',
            context: this,
            data: {item_id: itemID},
            success: function(response) {
                if (response.status == 'ok') {
                    if (response.current_is_approved && !response.newer_available) {
                        markLabelAsPrinted.call(this);
                        window.open(response.label_url, '_blank');
                    } else {
                        showWarnings(response);
                    }
                }
            }
        });
    });

    function showWarnings(response) {
        // Shows the modal
        $('#label-warning-modal').modal('show');

        // Updates the label download button with label data
        $('#download-label').prop('href', response.label_url);
        $('#download-label').attr('data-item-id', response.item_id);

        if (!response.current_is_approved && !response.current_is_rejected) {
            // Warns that current label is pending
            $('#label-warning-modal .current_not_approved').removeClass('hidden');
        }

        if (response.current_is_rejected) {
            // Warns that current label is rejected
            $('#label-warning-modal .current_is_rejected').removeClass('hidden');
        }

        // If a newer label is available
        if (response.newer_available) {
            // Warns that a newer label is available
            $('#label-warning-modal .newer_available').removeClass('hidden');

            if (response.latest_is_rejected)  {
                // Warns that the newer label has been rejected
                $('#label-warning-modal .latest_is_rejected').removeClass('hidden');
            }

            if (!response.latest_is_approved && !response.latest_is_rejected) {
                // Warns that the newer label is pending
                $('#label-warning-modal .latest_not_approved').removeClass('hidden');
            }

            if (response.latest_is_approved) {
                // Updates the latest label download button with label data
                $('#download-latest-label').prop('href', response.latest_label_url);
                $('#download-latest-label').attr('data-item-id', response.item_id);

                // Shows the button to download new, approved label
                $('#label-warning-modal .download_latest_label').removeClass('hidden');
            }
        }
    }
})();
