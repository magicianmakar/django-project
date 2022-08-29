jQuery(function () {

        $('#purchase-order-credits').click(function (e) {
            e.preventDefault();

            $('#modal-add-fulfill-limit').modal('show');
        });

        $('#purchase-order-credits-sd').click(function (e) {
            e.preventDefault();

            $('#modal-add-sd-orders-limit').modal('show');
        });
    });
