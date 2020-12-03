function basketCalculateShipping(country_code,province) {
        $.ajax({
            url: api_url('basket_calculate_shipping_cost', 'supplements'),
            type: "POST",
            data: JSON.stringify({
                'country_code': country_code,
                'province': province
            }),
            dataType: 'json',
            contentType: 'application/json',
            success: function (api_data) {

                var total_shipping_cost = api_data.shippings[0].shipping_cost;
                var checkout_total=parseFloat($('.checkout-total').html());
                $('#basket-modal-make-payment .shipping-cost').html('$'+total_shipping_cost);
                $('#basket-modal-make-payment .total-cost').html('$'+parseFloat(total_shipping_cost+checkout_total));

                $('#basket-modal-make-payment').modal('show');
                $('#basket-make-payment-confirm').off('click').click(function () {
                    //$('#basket-modal-make-payment').modal('hide');
                    $('#basket-make-payment-confirm').html($('#basket-make-payment-confirm').data('loading-text'));
                    basketMakePayment();
                });

            },
            error: function (api_data) {
                toastr.warning(getAjaxError(api_data));

                $('#basket-make-payment-confirm').html($('#basket-make-payment-confirm').data('default-text'));
            }
        });
    }

function basketMakePayment() {
    var data=$('#checkout-form').serialize();
    $.ajax({
        url: api_url('basket-make-payment', 'supplements'),
        type: "POST",
        data: data,
        dataType: 'json',
        success: function (data) {
            if (data.success) {
                msg = data.success;
                toastr.success(msg);
                window.location=app_link('supplements/my/order/list');
            }
        },
        error: function (api_data) {
            toastr.warning(getAjaxError(api_data));
            $('#basket-make-payment-confirm').html($('#basket-make-payment-confirm').data('default-text'));
        }

    });
}

$(document).ready(function () {
    'use strict';

    $('.select-country').chosen({
        search_contains: true
    });

    $('.select-country').trigger('change');

    $(".basket-checkout").click(function () {
        var country_code = $('#shipping_country').val();
        var province = $('#shipping_state').val();

        basketCalculateShipping(country_code,province);
    });

});
