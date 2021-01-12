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
    ChurnZero.push(['trackEvent', 'Auto Order Placed', 'supplement']);

    var lenOrders = $('#modal-make-payment .supplement-item-payment').length;

    if (!lenOrders) {
        toastr.warning("Please select orders for processing.");
        return;
    }

    var msg = "Preparing to pay for " + lenOrders + " ";
    msg += makePlural('item', lenOrders);
    msg += ".";

    toastr.info(msg);

    data = {
        'order_data_ids': orderDataIds,
        'store_id': storeId,
        'store_type': storeType,
    };

    var shippingService = $('[name="shipping_service"]:checked').val();
    if (shippingService) {
        data['shipping_service'] = shippingService;
    }

    $.ajax({
        url: api_url('make-payment', 'supplements'),
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
        }
    });
}

function formatCurrency(amount) {
    var currencyTemplate = Handlebars.compile(storePriceFormat);
    return currencyTemplate({amount: amount});
}

function makeData(orderDataIds) {
    var getLineItem = function(supplementElem) {
        var unitPrice = supplementElem.attr('line-price');
        var quantity = supplementElem.attr('line-quantity');

        var weight = 0;
        if (supplementElem.attr('weight') != "False") {
            weight = parseFloat(supplementElem.attr('weight'));
        }

        return {
            orderNumber: supplementElem.parents('.line').attr('order-number'),
            title: supplementElem.attr('line-title') + ' ('+ supplementElem.attr('pl-supplement-title') + ')',
            unitPrice: formatCurrency(unitPrice),
            quantity: quantity,
            amount: parseFloat(unitPrice) * quantity,
            weight: weight
        };
    };

    var data = {items: [], total: 0.0, total_weight: 0};
    $.each(orderDataIds, function(i, item) {
        line = $("div.payment-btn-wrapper[order-data-id=" + item + "]");

        line.find('.supplement-items li').each(function() {
            var lineItem = getLineItem($(this));
            data.total_weight += lineItem.weight;
            data.total += lineItem.amount;
            lineItem.amount = formatCurrency(lineItem.amount);
            data.items.push(lineItem);
        });
    });
    data.storeType = window.storeType;
    data.storeId = STORE_ID;
    data.total_weight = parseFloat(data.total_weight.toFixed(2));
    return data;
}

function makePayment(orderDataIds) {
    $.ajax({
        url: api_url('calculate_shipping_cost', 'supplements'),
        type: "POST",
        data: JSON.stringify({
            'order_data_ids': orderDataIds,
            'store_type': window.storeType
        }),
        dataType: 'json',
        contentType: 'application/json',
        success: function (api_data) {
            var shippingsCount = api_data.shippings.length;
            for (var i = 0; i < shippingsCount; i++) {
                api_data.shippings[i].currency_shipping_cost = formatCurrency(api_data.shippings[i].shipping_cost.toFixed(2));
            }

            var data = makeData(orderDataIds);
            data.currency_total_shipping_cost = api_data.shippings[0].currency_shipping_cost;
            data.currency_total = formatCurrency((data.total + api_data.shippings[0].shipping_cost).toFixed(2));

            var makePaymentTemplate = Handlebars.compile($("#id-make-payment-template").html());
            var html = makePaymentTemplate(data);

            $('#modal-make-payment tbody').empty().append(html);
            $('#modal-make-payment').modal('show');
            $('#id-make-payment-confirm').off('click').click(function () {
                $('#modal-make-payment').modal('hide');
                userHasBilling().then(function (result) {
                    doMakePayment(orderDataIds, data.storeId, data.storeType);
                }).catch(function (error){
                    return;
                });
            });

            $('#modal-make-payment .shipping-service').remove();
            if (shippingsCount > 1) {
                var servicesTemplate = Handlebars.compile($("#shipping-services-template").html());
                $('#modal-make-payment table').after(servicesTemplate(api_data));
                $('#modal-make-payment [name="shipping_service"]').off('change').on('change', function() {
                    var serviceId = $(this).attr('data-service-id');
                    for (var i = 0; i < shippingsCount; i++) {
                        if (serviceId == api_data.shippings[i].service_id) {

                            $('#modal-make-payment .shipping-cost').text(
                                api_data.shippings[i].currency_shipping_cost
                            );
                            $('#modal-make-payment .total-cost').text(
                                formatCurrency((data.total + api_data.shippings[i].shipping_cost).toFixed(2))
                            );
                            break;
                        }
                    }
                });
            }
        },
        error: function (api_data) {
            toastr.warning(getAjaxError(api_data));
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

function userHasBilling() {
    return new Promise(function (resolve, reject) {
        $.ajax({
            url: api_url('billing-info', 'supplements'),
            type: 'GET',
            success: function(data) {
                if (data.success) {
                    resolve();
                } else {
                  toastr.error("Please enter your billing information on the Billing tab.", "Billing Not Found!");
                  reject();
                }
            },
            error: function(data) {
                displayAjaxError('Billing', data);
            }
        });
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
        makePayment([orderDataId]);
    });

    $(".pay-selected-lines").click(function (e) {
        e.preventDefault();
        var country_code = $(this).parents('.order').find('.shipping-country-code').attr('shipping-country-code');
        var province_code = $(this).parents('.order').find('.shipping-province-code').attr('shipping-province-code');
        var deletedProducts = [];
        var orderDataIds = [];

        $(this).parents('.order').find('.line-checkbox').each(function (i, item) {
            var line = $(item).parents('.line');
            line.find('.payment-btn-wrapper .supplement-items li').each(function() {
                if ($(this).attr("is-deleted") === "true") {
                    deletedProducts.push($(this).attr('line-title'));
                }
            });
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
            makePayment(orderDataIds);
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

    $('.payment-btn-wrapper .supplement-items').each(function() {
        var btn = $(this).siblings('.pay-for-supplement');
        var btnWrapper = $(this).parents('.payment-btn-wrapper');
        $(this).find('li').each(function() {
            if ($(this).attr('is-deleted') === 'true') {
                btn.attr('is-deleted', 'true');
                btnWrapper.attr('is-deleted', 'true');
                btnWrapper.attr('title', 'This supplement has been deleted');
            }

            if ($(this).attr('is-approved') === 'false') {
                btn.prop('disabled', true);
                btnWrapper.attr('title', 'Approved label not found');
                btn.parents('.bundle-items').siblings().find('.line-checkbox').prop('disabled', true);
            }
        });
    });
});
