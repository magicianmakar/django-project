function loadCheckbox() {
    var elems = Array.prototype.slice.call(document.querySelectorAll('.js-switch'));
    elems.forEach(function(html) {
        if (html.nextElementSibling.className.indexOf('switchery') > -1) {
            return;
        }
        var switchery = new Switchery(html, {
            color: '#93c47d',
            size: 'small'
        });
    });
}

var formatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
});
function formatUSD(amount) {
    return formatter.format(parseFloat(amount));
}

function reloadPLTableStripes() {
    var isActive = false;
    var currentKey = null;
    $('.supplement-item-payment').removeClass('active').each(function() {
        var newKey = $(this).attr('order-id');
        if (newKey !== currentKey) {
            currentKey = newKey;
            isActive = !isActive;
        }

        if (isActive) {
            $(this).addClass('active');
        }
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

var taxesCache = {};
var taxRunning = false;
var taxOrderIDs = [];
function getOrderTax(tdElem) {
    var orderID = tdElem.parents('tr[supplement-order-data-id]').attr('order-id');

    // Avoid calling ajax if we already have taxes
    var serviceCode = $('input[type="radio"][name="shipping_service_' + orderID + '"]:checked').val() || '';
    var taxesCacheKey = orderID + '_' + serviceCode;
    var taxes = taxesCache[taxesCacheKey];
    if (taxes) {
        tdElem.find('.tax-cost').data('cost', taxes.cost).text(taxes.currency_cost);
        calculateTotals();
        return;
    }

    tdElem.find('.sk-spinner').removeClass('hidden');
    if (taxRunning) {
        taxOrderIDs.push(orderID);
    } else {
        getTax(orderID);
    }
}

function getTax(orderID) {
    taxRunning = true;
    $.ajax({
        url: api_url('order-taxes', 'supplements'),
        type: "POST",
        data: JSON.stringify({
            'store_type': window.storeType,
            'store_id': STORE_ID,
        }),
        context: {
            order_id: orderID,
            td_element: $('tr[order-id="' + this.order_id + '"]').find('.tax'),
        },
        dataType: 'json',
        contentType: 'application/json',
        beforeSend: function(xhr, settings) {
            this.td_element.find('.sk-spinner').removeClass('hidden');

            var orderDataIds = $('#modal-order-detail tr[order-id="' + this.order_id + '"]').map(function(i, elem) {
                return $(elem).attr('supplement-order-data-id');
            }).get();

            var selectedShippings = {};
            $('input[type="radio"][name="shipping_service_' + this.order_id + '"]:checked').each(function() {
                selectedShippings[$(this).attr('name').replace('shipping_service_', '')] = $(this).val();
            });

            var payTaxes = {};
            $('input[type="checkbox"][name^="pay_taxes_' + this.order_id + '"]').each(function() {
                payTaxes[$(this).attr('name').replace('pay_taxes_', '')] = $(this).is(':checked');
            });

            settings.data = JSON.parse(settings.data);
            settings.data['order_data_ids'] = orderDataIds;
            settings.data['pay_taxes'] = payTaxes;
            settings.data['shippings'] = selectedShippings;
            settings.data = JSON.stringify(settings.data);
        },
        success: function (data) {
            var details = formatAPIDetails(data);
            var orderDetailTemplate = Handlebars.compile($("#id-order-detail-template").html());
            var orderElements = orderDetailTemplate({'orders': details});
            $(orderElements).each(function() {
                if (this.nodeName.toLowerCase() !== 'tr') {
                    return;
                }

                var orderDataID = $(this).attr('supplement-order-data-id');
                $('[supplement-order-data-id="' + orderDataID + '"]').replaceWith($(this));
            });
            loadCheckbox();
            calculateTotals();

            var newOrderID = taxOrderIDs.shift();
            if (newOrderID) {
                getTax(newOrderID);
            } else {
                taxRunning = false;
            }
        },
        complete: function() {
            this.td_element.find('.sk-spinner').addClass('hidden');
        }
    });
}

function processOrders(orderDataIds, finish) {
    if (orderDataIds.length === 0) {
        toastr.warning("Please select orders for processing.");
        return;
    }

    finish = typeof(finish) !== 'undefined' ? finish : true;

    var selectedShippings = {};
    $('input[type="radio"][name^="shipping_service_"]:checked').each(function() {
        selectedShippings[$(this).attr('name').replace('shipping_service_', '')] = $(this).val();
    });

    var payTaxes = {};
    $('input[type="checkbox"][name^="pay_taxes_"]').each(function() {
        payTaxes[$(this).attr('name').replace('pay_taxes_', '')] = $(this).is(':checked');
    });

    data = {
        'order_data_ids': orderDataIds,
        'store_type': window.storeType,
        'store_id': STORE_ID,
        'shippings': selectedShippings,
        'pay_taxes': payTaxes,
    };

    if (!finish) {
        data['validate'] = true;
    }

    userHasBilling().then(function() {
        $.ajax({
            url: api_url('process-orders', 'supplements'),
            type: "POST",
            data: JSON.stringify(data),
            dataType: 'json',
            contentType: 'application/json',
            beforeSend: function() {
                $('#modal-order-detail').modal('show');
                $('#modal-order-detail .modal-content').addClass('loading');
                $('#modal-order-detail .place-label-orders').addClass('hidden');
            },
            success: function (data) {
                var details = formatAPIDetails(data);
                var orderDetailTemplate = Handlebars.compile($("#id-order-detail-template").html());
                $('#modal-order-detail tbody').empty().append(orderDetailTemplate({'orders': details}));
                loadCheckbox();
                calculateTotals();

                if (sub_conf.taxesEnabled) {
                    $('.tax').each(function() {
                        if (!$(this).find('[type="checkbox"]').is(':checked')) return;
                        var cost = $(this).find('.tax-cost').data('cost');
                        if (cost || cost === 0) return;
                        if ($(this).parents('tr').find('.text-danger').length) return;
                        getOrderTax($(this));
                    });
                } else {
                    $('.tax-view').css('display', 'none');
                }
            },
            error: function(data) {
                $('#modal-order-detail').modal('hide');
                swal({
                    title: 'Place Private Label Orders',
                    text: data.responseJSON.error,
                    type: 'warning',
                    html: true,
                });
            },
            complete: function() {
                $('#modal-order-detail .modal-content').removeClass('loading');
                $('#modal-order-detail .place-label-orders').removeClass('hidden');
            }
        });
    });
}

function formatAPIDetails(data) {
    var orderID;
    var selectedShippings = {};
    for (orderID in data.shippings) {
        for (var i = 0, iLength = data.shippings[orderID].length; i < iLength; i++) {
            var cost = parseFloat(data.shippings[orderID][i].shipping_cost);
            data.shippings[orderID][i].currency_shipping_cost = formatUSD(cost);
            data.shippings[orderID][i].currency_shipping_cost = formatUSD(cost);
            data.shippings[orderID][i].shipping_cost = cost;

            if (data.shippings[orderID][i].selected) {
                selectedShippings[orderID] = $.extend({}, data.shippings[orderID][i]);
            }
        }
    }

    for (orderID in data.taxes) {
        if (isNaN(data.taxes[orderID].taxes)) {
            data.taxes[orderID]['cost'] = '';
            data.taxes[orderID]['currency_cost'] = '';
            continue;
        }

        data.taxes[orderID]['cost'] = data.taxes[orderID].duties;
        data.taxes[orderID]['cost'] += data.taxes[orderID].taxes;
        data.taxes[orderID]['currency_cost'] = formatUSD(data.taxes[orderID]['cost']);

        var service = selectedShippings[orderID].service || {};
        var serviceCode = service.service_code || '';
        taxesCache[orderID + '_' + serviceCode] = $.extend(true, {}, data.taxes[orderID]);
    }

    var details = {};
    for (var j = 0, jLength = data.orders_status.length; j < jLength; j++) {
        var orderStatus = data.orders_status[j];
        if (!details[orderStatus.order_id]) {
            details[orderStatus.order_id] = {
                'shippings': data.shippings[orderStatus.order_id] || [],
                'tax': data.taxes[orderStatus.order_id] || {},
                'items': []
            };

            // Push 1 notification for each order
            if (orderStatus.placed && ChurnZero) {
                ChurnZero.push(['trackEvent', 'Auto Order Placed', 'supplement']);
            }
        }

        if (orderStatus.supplements && orderStatus.supplements.length) {
            for (var s = 0, sLength = orderStatus.supplements.length; s < sLength; s++) {
                var supplement = orderStatus.supplements[s];
                var newOrderStatus = $.extend(true, {}, orderStatus, {supplement: supplement});
                if (supplement.price) {
                    newOrderStatus.supplement.price = formatUSD(supplement.price);
                }
                if (supplement.subtotal) {
                    newOrderStatus.supplement.currency_subtotal = formatUSD(supplement.subtotal);
                }

                details[orderStatus.order_id].items.push(newOrderStatus);
            }
        } else {
            details[orderStatus.order_id].items.push(orderStatus);
        }
    }
    return details;
}

function calculateTotals() {
    var taxesTotalCost = 0;
    var shippingsTotalCost = 0;
    var productsTotalCost = 0;
    $('.order-total').each(function() {
        var orderID = $(this).data('order-id');
        var shippingCost = parseFloat($('[name="shipping_service_' + orderID + '"]:checked').data('cost') || 0);
        var taxesCost = parseFloat($('.tax-' + orderID + ':not(.hidden)').data('cost') || 0);
        var countProducts = 0;
        var productsCost = $('.product-cost-' + orderID).map(function(i, elem) {
            var cost = $(elem).data('cost');
            if (cost) {
                cost = parseFloat(cost);
                if (cost >= 0) {
                    countProducts += 1;
                    return cost;
                }
            }
            return 0;
        }).get().reduce(function(a, b) {
            return a + b;
        });

        taxesTotalCost += taxesCost;
        shippingsTotalCost += shippingCost;
        productsTotalCost += productsCost;

        if (countProducts) {
            $(this).text(formatUSD(productsCost + shippingCost + taxesTotalCost));
        }
    });


    $('#supplement-products-total').text(formatUSD(productsTotalCost));
    $('#supplement-shipping-total').text(formatUSD(shippingsTotalCost));
    $('#supplement-taxes-total').text(formatUSD(taxesTotalCost));
    $('#supplement-orders-total').text(formatUSD(productsTotalCost + shippingsTotalCost + taxesTotalCost));

    reloadPLTableStripes();
}

$('#modal-order-detail').on('change', '.shipping-service [type="radio"]', function() {
    var tdElem = $(this).parents('tr[supplement-order-data-id]').find('.tax');
    tdElem.find('.tax-cost').data('cost', 0).text('');

    if (tdElem.find('[type="checkbox"]').is(':checked')) {
        getOrderTax(tdElem);
    } else {
        calculateTotals();
    }
});

$('#modal-order-detail .place-label-orders').on('click', function(e) {
    e.preventDefault();

    var orderDataIds = $('#modal-order-detail tr[supplement-order-data-id]').map(function(i, elem) {
        return $(elem).attr('supplement-order-data-id');
    }).get();
    processOrders(orderDataIds);
});

$('#modal-order-detail').on('change', '.tax [type="checkbox"]', function() {
    var tdElem = $(this).parents('.tax');
    var spanElem = tdElem.find('.tax-cost');
    if ($(this).is(':checked')) {
        spanElem.removeClass('hidden');
        if (!spanElem.data('cost') || spanElem.data('cost') !== 0) {
            getOrderTax(tdElem);
        } else {
            calculateTotals();
        }
    } else {
        spanElem.addClass('hidden');
        calculateTotals();
    }
});

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

$(document).ready(function () {
    'use strict';

    $(".pay-for-supplement").click(function () {
        var orderDataId = $(this).parent().attr('order-data-id');
        processOrders([orderDataId], false);
    });

    $(".pay-selected-lines").click(function (e) {
        e.preventDefault();
        var orderDataIds = [];
        $(this).parents('.order').find('.line-checkbox:checkbox:checked').each(function (i, item) {
            var line = $(item).parents('.line');
            if (line.attr("is-pls") === "true") {
                orderDataIds.push(line.attr('order-data-id'));
            }
        });
        if (orderDataIds.length) {
            processOrders(orderDataIds, false);
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
