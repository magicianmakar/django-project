var orderItemsAlibaba = (function() {
    'use strict';

    var Currency = {
        storeFormat: config.currencyFormat,
        init: function() {
            if (!this.storeFormat) {
                this.storeFormat = '';
            }
            this.defineFormat(this.storeFormat);
        },
        formatTypes: {
            decimals: {
                without: function(value) {
                    // Only uses if no_decimals on format
                    return value.toFixed(0);
                },
                default: function(value) {
                    // Uses if there is no decimals definition on format
                    return value.toFixed(2);
                }
            },
            separator: {
                default: function(value) {
                    // No separator is defined
                    return value.replace(/(\d)(?=(\d{3})+(?:\.\d+)?$)/g, '$1,');
                },
                comma: function(value) {
                    // For when comma_separator is present on format
                    var separatedValue = value.replace(/(\d)(?=(\d{3})+(?:\.\d+)?$)/g, '$1.');
                    return separatedValue.replace(/\.(\d{1,2})?$/, ',$1');
                },
                space: function(value) {
                    // For when space_separator is present on format
                    var separatedValue = value.replace(/(\d)(?=(\d{3})+(?:\.\d+)?$)/g, '$1 ');
                    return separatedValue.replace(/\.(\d{1,2})?$/, ',$1');
                },
                apostrophe: function(value) {
                    // For when apostrophe_separator is present on format
                    return value.replace(/(\d)(?=(\d{3})+(?:\.\d+)?$)/g, '$1\'');
                }
            }
        },
        decimalsFormat: function(baseValue) {
            return this.formatTypes.decimals.default(baseValue);
        },
        separatorFormat: function(baseValue) {
            return this.formatTypes.separator.default(baseValue);
        },
        defineFormat: function(newFormat) {
            if (newFormat.trim() == '') {
                // Setting default format if empty
                newFormat = '${{ amount }}';
            }
            this.storeFormat = newFormat;

            if (this.storeFormat.indexOf('no_decimals') > -1) {
                this.decimalsFormat = this.formatTypes.decimals.without;
            } else {
                this.decimalsFormat = this.formatTypes.decimals.default;
            }

            if (this.storeFormat.indexOf('comma_separator') > -1) {
                this.separatorFormat = this.formatTypes.separator.comma;
            } else if (this.storeFormat.indexOf('space_separator') > -1) {
                this.separatorFormat = this.formatTypes.separator.space;
            } else if (this.storeFormat.indexOf('apostrophe_separator') > -1) {
                this.separatorFormat = this.formatTypes.separator.apostrophe;
            } else {
                this.separatorFormat = this.formatTypes.separator.default;
            }
        },
        format: function(baseValue, noSign) {
            var decimalsValue = this.decimalsFormat(baseValue),
                value = this.separatorFormat(decimalsValue);

            if (noSign) {
                return value;
            } else {
                return this.storeFormat.replace(/(\{\{ ?\S+ ?\}\})/, value);
            }
        }
    };
    Currency.init();
    Handlebars.registerHelper("currencyFormat", function(amount) {
        if (!amount) return '';
        return Currency.format(parseFloat(amount));
    });

    var formatter = new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
    });
    function formatUSD(amount) {
        return formatter.format(parseFloat(amount));
    }
    function updateTotal(shippingElem) {
        var orderTotalElem = shippingElem.parents('.alibaba-item-payment').find('.order-total');

        var shippingCost = parseFloat(shippingElem.find('option:selected').attr('data-cost') || 0);
        var productsCost = parseFloat(orderTotalElem.attr('product-total'));
        if (isNaN(productsCost)) {
            productsCost = 0;
        }
        orderTotalElem.text(formatUSD(shippingCost + productsCost));
    }
    function loadTooltip(elem) {
        console.log(elem);
        elem.each(function() {
            var wrapper = $(this);
            if (wrapper.prop('offsetWidth') < wrapper.prop('scrollWidth')) {
                var options = {
                    container: this,
                    template: '<div class="tooltip" style="margin: 20px 0 0 0;" role="tooltip">' +
                                '<div class="tooltip-arrow" style="left: 50%;"></div>' +
                                '<div class="tooltip-inner"></div>' +
                              '</div>'
                };
                if (typeof ($.fn.bootstrapTooltip) === 'undefined') {
                    $(this).tooltip(options);
                } else {
                    $(this).bootstrapTooltip(options);
                }
            } else {
                $(this).attr('title', '');
            }
        });
    }
    function reloadTableStripes() {
        var isActive = false;
        var currentKey = null;
        $('.alibaba-item-payment').removeClass('active').each(function() {
            var newKey = $(this).attr('order-id') + '_' + $(this).attr('split-id');
            if (newKey !== currentKey) {
                currentKey = newKey;
                isActive = !isActive;
            }

            if (isActive) {
                $(this).addClass('active');
            }
        });
    }

    function formatAjaxOrders(orders) {
        var orderDetailTemplate = Handlebars.compile($("#alibaba-order-detail-template").html());
        for (var o = 0, oLength = orders.length; o < oLength; o++) {
            orders[o]['product_total'] = 0;

            for (var p = 0, pLength = orders[o]['products'].length; p < pLength; p++) {
                orders[o]['product_total'] += parseFloat(orders[o]['products'][p]['variant']['total_price']);
            }
        }
        var ordersElem = $(orderDetailTemplate({'orders': orders}));
        var orderKeys = ordersElem.map(function(k, v) { return $(v).attr('data-order-id') + ';' + $(v).attr('data-source-id'); }).get();
        $('#modal-alibaba-order-detail tbody').append(ordersElem);

        loadTooltip($('#modal-alibaba-order-detail tbody .itooltip'));
        for (var i = 0, iLength = orderKeys.length; i < iLength; i++) {
            var orderKey = orderKeys[i].split(';');
            var dataOrderId = orderKey[0];
            var dataSourceId = orderKey[1];
            var selector = '[data-order-id="' + dataOrderId + '"][data-source-id="' + dataSourceId + '"]';
            if ($(selector).length > 1) {
                $(selector + ':first').remove();
            }
            updateTotal($(selector + ' .shipping-service'));
        }
    }

    function processOrdersAlibaba(orderDataIds, orderShippings, orderSplits, useCache, finish) {
        var data = {
            'order_data_ids': orderDataIds,
            'store_type': window.storeType,
            'store_id': STORE_ID,
        };

        if (orderShippings) {
            data['order_shippings'] = orderShippings;
        }

        if (orderSplits) {
            data['order_splits'] = orderSplits;
        }

        if (!finish) {
            data['validate'] = true;
        }

        if (useCache) {
            data['use_cache'] = true;
        }

        return $.ajax({
            url: api_url('process-orders', 'alibaba'),
            type: 'POST',
            data: JSON.stringify(data),
            dataType: 'json',
            contentType: 'application/json',
            beforeSend: function() {
                if ($('#modal-alibaba-order-detail:hidden').length > 0) {
                    $('#modal-alibaba-order-detail tbody').empty();
                }

                $('[name="alibaba_pay"]:not(:checked)').parents('.alibaba-item-payment').remove();
                $('[name="alibaba_pay_all"]').prop('checked', true);
                $('#modal-alibaba-order-detail').modal('show');

                $('#modal-alibaba-order-detail .place-alibaba-orders').removeClass('hidden');
                $('#modal-alibaba-order-detail .reload-alibaba-orders').addClass('hidden');
                $('#modal-alibaba-order-detail .pay-alibaba-orders').addClass('hidden').attr('data-orders', '');
            },
            success: function(data) {
                formatAjaxOrders(data.orders);
                if (data.alibaba_order_ids) {
                    $('#modal-alibaba-order-detail .btn:not(.btn-danger)').addClass('hidden');
                    $('#modal-alibaba-order-detail .pay-alibaba-orders').removeClass('hidden').attr(
                        'data-orders', data.alibaba_order_ids.join(',')
                    );
                }
            },
            error: function(data) {
                displayAjaxError('Alibaba Ordering', data);

                if (data.orders) {
                    formatAjaxOrders(orders);
                }
            }
        });
    }

    $('[supplier-type="alibaba"]').each(function() {
        $(this).attr('order-data-id');
    });

    $('#modal-alibaba-order-detail').on('change', '.shipping-service', function() {
        updateTotal($(this));
    }).on('change', '[name="alibaba_pay"]', function() {
        if ($('[name="alibaba_pay"]:not(:checked)').length > 0) {
            $('#modal-alibaba-order-detail .place-alibaba-orders').addClass('hidden');
            $('#modal-alibaba-order-detail .reload-alibaba-orders').removeClass('hidden');
            $('[name="alibaba_pay_all"]').prop('checked', false);
        } else {
            $('#modal-alibaba-order-detail .place-alibaba-orders').removeClass('hidden');
            $('#modal-alibaba-order-detail .reload-alibaba-orders').addClass('hidden');
            $('[name="alibaba_pay_all"]').prop('checked', true);
        }
    });

    $('[name="alibaba_pay_all"]').on('change', function() {
        if ($(this).is(':checked')) {
            $('[name="alibaba_pay"]').prop('checked', true);
        } else {
            $('[name="alibaba_pay"]').prop('checked', false);
        }
        $('[name="alibaba_pay"]:first').trigger('change');
    });

    $('.place-alibaba-orders, .reload-alibaba-orders').on('click', function(e) {
        e.preventDefault();
        if ($('#modal-alibaba-order-detail .modal-content').hasClass('loading')) {
            return;
        }

        var orderDataIds = {};
        var orderSplits = {};
        $('[name="alibaba_pay"]:checked').parents('.alibaba-item-payment').each(function() {
            var elem = $(this);
            var order = elem.attr('order-id');
            if (!orderSplits[order]) {
                orderSplits[order] = {};
                orderDataIds[order] = [];
            }

            var split = elem.attr('split-id');
            if (!orderSplits[order][split]) {
                orderSplits[order][split] = {};
            }

            var orderDataId = elem.attr('data-order-id');
            if (!orderSplits[order][split][orderDataId]) {
                orderSplits[order][split][orderDataId] = [];
            }

            orderSplits[order][split][orderDataId].push(elem.attr('data-source-id'));
            orderDataIds[order].push(orderDataId);
        });

        var orderShippings = {};
        $('#modal-alibaba-order-detail select.shipping-service').each(function() {
            var order = $(this).prop('name').replace('shipping_service_', '');
            orderShippings[order] = $(this).val();
        });

        var button = $(this);
        var orderSplit;
        $('#modal-alibaba-order-detail .modal-content').addClass('loading');
        $.when.apply($, $.map(orderDataIds, function(orderIds, key) {
            orderSplit = {};
            orderSplit[key] = orderSplits[key];
            return processOrdersAlibaba(
                orderDataIds[key],
                orderShippings,
                orderSplit,
                true,
                button.hasClass('place-alibaba-orders')
            );
        })).always(function(){
            $('#modal-alibaba-order-detail .modal-content').removeClass('loading');
            reloadTableStripes();
        });
    });

    $('#modal-alibaba-order-detail .pay-alibaba-orders').on('click', function(e) {
        e.preventDefault();

        $.ajax({
            url: api_url('pay-orders', 'alibaba'),
            type: 'POST',
            data: JSON.stringify({
                'order_data_ids': $(this).attr('data-orders').split(','),
                'store_type': window.storeType,
                'store_id': STORE_ID,
            }),
            dataType: 'json',
            contentType: 'application/json',
            beforeSend: function() {
                $('#modal-alibaba-order-detail .modal-content').addClass('loading');
            },
            success: function(data) {
                if (data.error) {
                    var errorLink = '';
                    if (data.action) {
                        errorLink = $('<a target="_blank">').attr(
                            'href', data.action
                        ).text(data.action_message).prop('outerHTML');
                    }

                    swal({
                        title: 'Payment Error',
                        text: data.error + ' ' + errorLink,
                        type: 'error',
                        html: true
                    });
                } else {
                    swal({
                        title: 'Payment Success',
                        text: 'Your orders are being processed',
                        type: 'success',
                    });
                }
            },
            complete: function() {
                $('#modal-alibaba-order-detail .modal-content').removeClass('loading');
            }
        });
    });

    function orderItemsAlibaba(orderDataIds) {
        if ($('#modal-alibaba-order-detail .modal-content').hasClass('loading')) {
            return;
        }

        var groupedOrderIds = {};
        for (var i = 0, iLength = orderDataIds.length; i < iLength; i++) {
            var order = orderDataIds[i].split('_')[1];

            if (!groupedOrderIds[order]) {
                groupedOrderIds[order] = [];
            }

            groupedOrderIds[order].push(orderDataIds[i]);
        }

        $('#modal-alibaba-order-detail .modal-content').addClass('loading');
        $.when.apply($, $.map(groupedOrderIds, function(orderIds, i) {
            return processOrdersAlibaba(orderIds);
        })).always(function(){
            $('#modal-alibaba-order-detail .modal-content').removeClass('loading');
            reloadTableStripes();
        });
    }

    return orderItemsAlibaba;
})();
