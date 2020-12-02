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
                $('#basket-modal-make-payment .shipping-cost').attr('data-shipping-cost', total_shipping_cost);
                $('#basket-modal-make-payment .total-cost').html('$'+parseFloat(total_shipping_cost+checkout_total));

                $('#basket-modal-make-payment').modal('show');
                $('#basket-make-payment-confirm').off('click').click(function () {
                    //$('#basket-modal-make-payment').modal('hide');
                    $('#basket-make-payment-confirm').html($('#basket-make-payment-confirm').data('loading-text'));
                    basketMakePayment(false);
                });

                $('#basket-calculate-taxes').off('click').click(function () {
                    //$('#basket-modal-make-payment').modal('hide');
                    if(!$('#pay_supplement_taxes').prop('checked')) {
                        toastr.info('Please choose to pay for Duties & Taxes');
                        return;
                    }
                    $('#basket-calculate-taxes').html($('#basket-calculate-taxes').data('loading-text'));
                    basketMakePayment(true);
                });

            },
            error: function (api_data) {
                toastr.warning(getAjaxError(api_data));

                $('#basket-make-payment-confirm').html($('#basket-make-payment-confirm').data('default-text'));
            }
        });
    }

function basketMakePayment(calculateTax) {
    var data=$('#checkout-form').serialize();
    if(calculateTax) {
        data = data + '&return_tax=true';
    }
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

            if(data.return_tax) {
                var taxes = parseFloat(data.taxes);
                var duties = parseFloat(data.duties);
                var total = parseFloat($('.checkout-total').html());

                if(data.is_US_Shipment) {
                    toastr.info('Duties & Taxes not applicable for U.S Shipments');
                }

                var shippingCost = parseFloat($('#basket-modal-make-payment .shipping-cost').attr('data-shipping-cost'));
                $('#basket-modal-make-payment .total-duties').html('$' + duties);
                $('#basket-modal-make-payment .total-taxes').html('$' + taxes);
                var totalCost = taxes + duties + total + shippingCost;                
                $('#basket-modal-make-payment .total-cost').html('$'+totalCost);
                $('#basket-calculate-taxes').html('Calculate Tax');
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
