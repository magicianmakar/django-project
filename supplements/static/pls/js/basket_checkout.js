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
                if (api_data.shippings[0].error) {
                    swal(api_data.shippings[0].error, '', "warning");
                    return;
                }
                var shippingsCount = api_data.shippings.length;
                for (var i = 0; i < shippingsCount; i++) {
                    api_data.shippings[i].currency_shipping_cost = '$'+api_data.shippings[i].shipping_cost.toFixed(2);
                }
                var total_shipping_cost = api_data.shippings[0].shipping_cost;
                var checkout_total=parseFloat($('.checkout-total').html());
                $('#basket-modal-make-payment .shipping-cost').html('$'+total_shipping_cost.toFixed(2));
                $('#basket-modal-make-payment .total-cost').html('$'+parseFloat(total_shipping_cost+checkout_total).toFixed(2));

                $('#basket-modal-make-payment').modal('show');
                $('#basket-make-payment-confirm').off('click').click(function () {
                    //$('#basket-modal-make-payment').modal('hide');
                    $('#basket-make-payment-confirm').html($('#basket-make-payment-confirm').data('loading-text'));
                    basketMakePayment();
                });

                var servicesTemplate = Handlebars.compile($("#shipping-services-template").html());
                $('#basket-modal-make-payment .shipping-service-selection').html(servicesTemplate(api_data));
                $('#basket-modal-make-payment [name="shipping_service"]').off('change').on('change', function() {
                    var serviceId = $(this).attr('data-service-id');
                    for (var i = 0; i < shippingsCount; i++) {
                        if (serviceId == api_data.shippings[i].service_id) {

                            $('#basket-modal-make-payment .shipping-cost').html(
                                '$'+parseFloat(api_data.shippings[i].shipping_cost).toFixed(2)
                            );
                            $('#basket-modal-make-payment .total-cost').html(
                                '$'+( parseFloat(checkout_total) + parseFloat(api_data.shippings[i].shipping_cost)).toFixed(2)
                            );
                            break;
                        }
                    }
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

    var shippingService = $('.shipping-service-selection [name="shipping_service"]:checked').val();
    if (shippingService) {
        data+='&shipping_service='+shippingService;
    }
    if ($('#shipping_address').prop('checked') == false ){
        data+='&shipping_address='+false;
    } else {
        data+='&shipping_address='+true;
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
        },
        error: function (api_data) {
            toastr.options = {
                "closeButton": true,
                "positionClass": "toast-top-right",
                "preventDuplicates": true,
                "timeOut": "20000",
                "extendedTimeOut": "20000"
              };
            toastr.error(getAjaxError(api_data));
            $('#basket-modal-make-payment button.close').trigger('click');
            $('#basket-make-payment-confirm').html($('#basket-make-payment-confirm').data('default-text'));
        }

    });
}

$("#shipping_address").click(function () {
    if ($('#shipping_address').prop('checked') == false ){
        $('.shipping-form').show();
        $("input[name=shipping_address_line1]").attr("required", true);
        $("input[name=shipping_state]").attr("required", true);
        $("input[name=shipping_zip_code]").attr("required", true);
        $("#shipping_country").prop("required", true);
        $("#billing_country").prop("required", false);
    } else {
        $('.shipping-form').hide();
        $("input[name=shipping_address_line1]").attr("required", false);
        $("input[name=shipping_state]").attr("required", false);
        $("input[name=shipping_zip_code]").attr("required", false);
        $("#shipping_country").prop("required", false);
        $("#billing_country").prop("required", true);
    }
});

$('.select-country').on('change', function(e) {
    $('.select-country').trigger("chosen:updated");
});

$(document).ready(function () {
    'use strict';

    $('.select-country').chosen({
        search_contains: true
    });

    $('.select-country').trigger('change');
    $('.shipping-form').hide();
    $('#shipping_address').prop('checked', true);

    $(".basket-checkout").click(function () {
        var country_code = '';
        var province = '';
        if ($('#shipping_address').prop('checked') == false ){
            country_code = $('#shipping_country').val();
            province = $('#shipping_state').val();
        } else {
            country_code = $('#billing_country').val();
            province = $('#billing_state').val();
        }

        if ( $('#checkout-form')[0].checkValidity() ) {
            basketCalculateShipping(country_code,province);
        } else {
            $('#checkout-form')[0].reportValidity();
        }


    });

});
