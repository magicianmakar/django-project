$(document).on('ready', function() {
    $('.order-refund').on('click', function(e) {
        e.preventDefault();

        var btn = $(this);
        swal({
            title: 'Refund Order',
            text: 'Refunds take time to process, Are you sure you want to ask for a refund?',
            type: "warning",
            showCancelButton: true,
            animation: false,
            cancelButtonText: "Cancel",
            confirmButtonText: 'Yes',
            confirmButtonColor: "#DD6B55",
            closeOnCancel: true,
            closeOnConfirm: false,
            showLoaderOnConfirm: true,
        },
        function(isConfirm) {
            if (isConfirm) {

                $.ajax({
                    type: 'POST',
                    url: api_url('refund', 'logistics'),
                    data: {'id': btn.data('id')},
                    context: btn,
                    success: function(data) {
                        toastr.success('Refund ' + data.order.refund_status);
                        swal.close();
                    },
                    error: function(data) {
                        displayAjaxError('Refund Order', data);
                    }
                });
            }
        });
    });
});
