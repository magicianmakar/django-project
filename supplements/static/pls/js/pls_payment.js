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
        }
    });
}

function makeData(orderDataIds) {
    var data = {};
    var items = [];
    var quantity, unitPrice, amount, total = 0.0, storeType, storeId;

    var currencyTemplate = Handlebars.compile(storePriceFormat);

    function formatCurrency(amount) {
        return currencyTemplate({amount: amount});
    }

    $.each(orderDataIds, function (i, item) {
        line = $("div.payment-btn-wrapper[order-data-id=" + item + "]");
        orderNumber = $(line).attr('order-number');
        unitPrice = $(line).attr('line-price');
        quantity = $(line).attr('line-quantity');
        amount = unitPrice * quantity;
        storeType = $(line).attr('store-slug');
        storeId = $(line).attr('store-id');

        items.push({
            title: $(line).attr('line-title'),
            orderNumber: orderNumber,
            unitPrice: formatCurrency(unitPrice),
            quantity: quantity,
            amount: formatCurrency(amount.toFixed(2))
        });

        total += amount;
    });
    data.total = formatCurrency(total.toFixed(2));
    data.items = items;
    data.storeType = storeType;
    data.storeId = storeId;
    return data;
}

function makePayment(orderDataIds) {
    var makePaymentTemplate = Handlebars.compile($("#id-make-payment-template").html());
    var data = makeData(orderDataIds);
    var html = makePaymentTemplate(data);
    $('#modal-make-payment tbody').empty().append(html);
    $('#modal-make-payment').modal('show');
    $('#id-make-payment-confirm').off('click').click(function () {
        $('#modal-make-payment').modal('hide');
        doMakePayment(orderDataIds, data.storeId, data.storeType);
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

$(document).ready(function () {
    'use strict';

    $(".pay-for-supplement").click(function () {
        var orderDataId = $(this).parent().attr('order-data-id');
        makePayment([orderDataId]);
    });

    $(".pay-selected-lines").click(function (e) {
        e.preventDefault();
        var orderDataIds = [];
        $('.line-checkbox:checkbox:checked').each(function (i, item) {
            var line = $(item).parents('.line');
            if (line.attr("is-pls") === "true") {
                orderDataIds.push(line.attr('order-data-id'));
            }
        });
        makePayment(orderDataIds);
    });

    $(".order-payout").on("blur", function () {
        var orderId = $(this).parent('.order-payout-wrapper').data('order-id');
        var referenceNumber = $(this).val();
        addOrderToPayout(orderId, referenceNumber);
    });

    var enableEditing = false;
    $("#payout-column").click(function () {
        if (enableEditing) {
            enableEditing = false;
            $(".order-payout").prop('disabled', enableEditing);
            $(this).attr('title',  "Disable editing");
        } else {
            enableEditing = true;
            $(".order-payout").prop('disabled', enableEditing);
            $(this).attr('title',  "Enable editing");
        }
    });
    $("#payout-column").trigger('click');
});
