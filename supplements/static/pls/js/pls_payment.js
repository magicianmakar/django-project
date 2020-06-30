function makePlural(word, length) {
    if (length === 1) {
        return word;
    }
    return word += "s";
}

function updateStatus(orderIds) {
    for (var i=0; i<orderIds.length; i++) {
        var info = orderIds[i];
        var line = $('.line[order-data-id="' + info.id + '"]');
        var lineInfo = line.find('.line-ordered');
        lineInfo.find('.badge').addClass('badge-primary').removeClass('badge-danger');
        lineInfo.find('.ordered-status').html(info.status);

        line.find('.pay-for-supplement').hide();
        line.find('.line-checkbox').attr('checked', false).attr('disabled', true);
    }
}

function doMakePayment(orderDataIds, storeId, storeType) {
    var lenOrders = orderDataIds.length;

    if (!lenOrders) {
        toastr.warning("Please select orders for processing.");
        return;
    }

    var msg = "Preparing to pay for " + lenOrders + " ";
    msg += makePlural('item', lenOrders);
    msg += ".";

    toastr.info(msg);

    var url = api_url('make-payment', 'supplements');
    data = {
        'order_data_ids': orderDataIds,
        'store_id': storeId,
        'store_type': storeType
    };
    $.ajax({
        url: url,
        type: "POST",
        data: JSON.stringify(data),
        dataType: 'json',
        contentType: 'application/json',
        success: function (data) {
            var orderStr;
            if (data.success) {
                updateStatus(data.successIds);
                orderStr = makePlural('item', data.success);
                msg = data.success + " " + orderStr + " sent for fulfillment.";
                toastr.success(msg);
            }

            if (data.error == 'rejected') {
                toastr.error(data.msg);
                return false;
            }

            if (data.error) {
                orderStr = makePlural('item', data.error);
                toastr.error(data.error + " " + orderStr + " failed.");
            }

            if (data.invalidCountry) {
                orderStr = makePlural('item', data.invalidCountry);
                msg = data.invalidCountry + " " + orderStr;
                msg += " had invalid shipping country.";
                msgStr = toastr.error(msg);
            }

            if (data.inventoryError) {
                orderStr = makePlural('item', data.inventoryError);
                msg = data.inventoryError + " " + orderStr;
                msg += " had not enough inventory.";
                msgStr = toastr.error(msg);
            }
        },
        error: function (data) {
            if (data.responseJSON["error"] === "billing") {
                toastr.error("Please enter your billing information on the Billing tab.");
            }
        }
    });
}

function formatCurrency(amount) {
        var currencyTemplate = Handlebars.compile(storePriceFormat);
        return currencyTemplate({amount: amount});
    }

function makeData(orderDataIds) {
    var data = {};
    var items = [];
    var quantity, unitPrice, amount, total = 0.0, storeType, storeId;
    var total_weight=0;

    $.each(orderDataIds, function (i, item) {
        line = $("div.payment-btn-wrapper[order-data-id=" + item + "]");
        orderNumber = $(line).attr('order-number');
        unitPrice = $(line).attr('line-price');
        quantity = $(line).attr('line-quantity');
        storeType = $(line).attr('store-slug');
        storeId = $(line).attr('store-id');

        if ($(line).attr('weight')!="False"){
            total_weight += parseFloat($(line).attr('weight'));
        }

        amount = parseFloat(unitPrice) * quantity ;

        items.push({
            title: $(line).attr('line-title'),
            orderNumber: orderNumber,
            unitPrice: formatCurrency(unitPrice),
            quantity: quantity,
            amount: formatCurrency(amount.toFixed(2))
        });

        total += amount;
    });
    data.total = total;
    data.items = items;
    data.storeType = storeType;
    data.storeId = storeId;
    data.total_weight = total_weight;
    return data;
}

function makePayment(orderDataIds,country_code,province_code) {
    var makePaymentTemplate = Handlebars.compile($("#id-make-payment-template").html());
    var data = makeData(orderDataIds);

    var url = api_url('calculate_shipping_cost', 'supplements');
    var post_data = {
        'country-code': country_code,
        'province-code': province_code,
        'total-weight': data.total_weight
    };
    $.ajax({
        url: url,
        type: "POST",
        data: JSON.stringify(post_data),
        dataType: 'json',
        contentType: 'application/json',
        success: function (api_data) {
            data.total_shipping_cost=formatCurrency(api_data.shipping_cost.toFixed(2));
            data.total = formatCurrency((data.total+api_data.shipping_cost).toFixed(2));

            var html = makePaymentTemplate(data);
            $('#modal-make-payment tbody').empty().append(html);
            $('#modal-make-payment').modal('show');
            $('#id-make-payment-confirm').off('click').click(function () {
                $('#modal-make-payment').modal('hide');
                doMakePayment(orderDataIds, data.storeId, data.storeType);
            });

        },
        error: function (api_data) {
            toastr.warning("Error calculating shipping");
        }
    });

}

function addOrderToPayout(orderId, referenceNumber) {
    var selector = '.order-payout-wrapper[data-order-id=' + orderId + '] input';
    var url = api_url('order-payout', 'supplements');
    data = {
        'order-id': orderId,
        'reference-number': referenceNumber
    };
    $.ajax({
        url: url,
        type: "POST",
        data: JSON.stringify(data),
        dataType: 'json',
        contentType: 'application/json',
        success: function (data) {
            $(selector).addClass('payout-success');
        },
        error: function (data) {
            $(selector).addClass('payout-error');
        }
    });
}

function addShippingCostToPayout(payoutId, cost) {
    var selector = '.shipping-cost-wrapper[data-payout-id=' + payoutId + '] input';
    var url = api_url('shipping-cost-payout', 'supplements');
    data = {
        'payout_id': payoutId,
        'cost': cost
    };
    $.ajax({
        url: url,
        type: "POST",
        data: JSON.stringify(data),
        dataType: 'json',
        contentType: 'application/json',
        success: function (data) {
            $(selector).addClass('payout-success');
        },
        error: function (data) {
            $(selector).addClass('payout-error');
        }
    });
}

function orderRejectionWarning(txt) {
    toastr.error('Order has been rejected');
    swal({
        title: "Order Rejected!",
        text: txt,
        type: "error",
        showCancelButton: true,
        showConfirmButton: false,
        cancelButtonText: "Close",
    });
}

$(document).ready(function () {
    'use strict';

    $(".pay-for-supplement").click(function () {
        var orderDataId = $(this).parent().attr('order-data-id');
        var country_code = $(this).parents('.order').find('.shipping-country-code').attr('shipping-country-code');
        var province_code = $(this).parents('.order').find('.shipping-province-code').attr('shipping-province-code');
        var deletedProduct = $(this).parent().attr('line-title');
        var txt = 'Your order contains deleted product (' + deletedProduct + ') & has been rejected.';

        // Reject order if a supplement is deleted
        if($(this).attr('is-deleted') == "true") {
            orderRejectionWarning(txt);
            return false;
        }
        makePayment([orderDataId],country_code, province_code);
    });

    $(".pay-selected-lines").click(function (e) {
        e.preventDefault();
        var order_id=$(this).attr('order-id');
        var country_code = $(this).parents('.order').find('.shipping-country-code').attr('shipping-country-code');
        var province_code = $(this).parents('.order').find('.shipping-province-code').attr('shipping-province-code');
        var deletedProducts = [];
        var orderDataIds = [];

        $(this).parents('.order').find('.line-checkbox').each(function (i, item) {
            var line = $(item).parents('.line');
            if (line.attr("is-deleted") === "true") {
                deletedProducts.push(line.attr('line-title'));
            }
        });

        if (deletedProducts.length) {
            var delProducts = deletedProducts.join(', ');
            var txt = 'Your order contains deleted product (' + delProducts + ') & has been rejected.';
            orderRejectionWarning(txt);
            return false;
        }

        $(this).parents('.order').find('.line-checkbox:checkbox:checked').each(function (i, item) {
            var line = $(item).parents('.line');
            if (line.attr("is-pls") === "true") {
                orderDataIds.push(line.attr('order-data-id'));
            }
        });
        if (orderDataIds.length) {
            makePayment(orderDataIds,country_code,province_code);
        } else {
            toastr.warning("Please select orders for processing.");
        }
    });

    $(".pay-all-lines").click(function (e) {
        e.preventDefault();
        $(this).parents('.order').find('.line-checkbox').not(":disabled").prop('checked',true);
        $(this).parents('.order').find('.pay-selected-lines').click();
    });

    $(".order-payout").on("blur", function () {
        var orderId = $(this).parent('.order-payout-wrapper').data('order-id');
        var referenceNumber = $(this).val();
        addOrderToPayout(orderId, referenceNumber);
    });

    $(".shipping-cost").on("blur", function () {
        var payoutId = $(this).parent('.shipping-cost-wrapper').data('payout-id');
        var cost = $(this).val();
        addShippingCostToPayout(payoutId, cost);
    });

    var enableEditing = false;
    $("#edit-column").click(function () {
        if (enableEditing) {
            enableEditing = false;
            $(".editable-column").prop('disabled', enableEditing);
            $(this).attr('title',  "Disable editing");
        } else {
            enableEditing = true;
            $(".editable-column").prop('disabled', enableEditing);
            $(this).attr('title',  "Enable editing");
        }
    });
    $("#edit-column").trigger('click');
});
