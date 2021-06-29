(function() {
    'use strict';

    var orders = {};
    var updatePromise;
    var order_update_tpl = Handlebars.compile($("#order-update-template").html());
    var disable_config_sync = false;

    var status_map = {
        "PLACE_ORDER_SUCCESS": "Awaiting Payment",
        "IN_CANCEL": "Awaiting Cancellation",
        "WAIT_SELLER_SEND_GOODS": "Awaiting Shipment",
        "SELLER_PART_SEND_GOODS": "Partial Shipment",
        "WAIT_BUYER_ACCEPT_GOODS": "Awaiting delivery",
        "WAIT_GROUP_SUCCESS": "Pending operation success",
        "FINISH": "Order Completed",
        "IN_ISSUE": "Dispute Orders",
        "IN_FROZEN": "Frozen Orders",
        "WAIT_SELLER_EXAMINE_MONEY": "Payment not yet confirmed",
        "RISK_CONTROL": "Payment being verified",
        "IN_PRESELL_PROMOTION": "Promotion is on",
        "FUND_PROCESSING": "Fund Processing",

        "BUYER_NO_SHOW": "Pickup cancelled buyer no show",
        "BUYER_REJECTED": "Pickup cancelled buyer rejected",
        "DELIVERED": "Delivered",
        "DIRECT_DEBIT": "Direct Debit",
        "EXTERNAL_WALLET": "Processed by PayPal",
        "IN_TRANSIT": "In transit",
        "MANIFEST": "Shipping Info Received",
        "NO_PICKUP_INSTRUCTIONS_AVAILABLE": "No pickup instruction available",
        "NOT_PAID": "Not Paid",
        "OUT_OF_STOCK": "Out of stock",
        "PENDING_MERCHANT_CONFIRMATION": "Order is being prepared",
        "PICKED_UP": "Picked up",
        "PICKUP_CANCELLED_BUYER_NO_SHOW": "Pickup cancelled buyer no show",
        "PICKUP_CANCELLED_BUYER_REJECTED": "Pickup cancelled buyer rejected",
        "PICKUP_CANCELLED_OUT_OF_STOCK": "Out of stock",
        "READY_FOR_PICKUP": "Ready for pickup",
        "SHIPPING_INFO_RECEIVED": "Shipping info received",

        "D_PENDING_PAYMENT": "Pending Payment",
        "D_PAID": "Confirmed Payment",
        "D_PENDING_SHIPMENT": "Pending Shipment",
        "D_SHIPPED": "Shipped"
    };

    P.config({
        cancellation: true
    });

    Number.prototype.bound = function(min, max) {
      return Math.min(Math.max(this, min), max);
    };

    $('.aliexpress-sync-btn').click(function(e) {
        window.extensionSendMessage({
            subject: 'getVersion',
        }, function(rep) {
            if (rep && rep.version) {
                $('.aliexpress-sync-btn').prop('updated-version', true);

                syncTrackedOrders();
            } else {
                upgradeWarning();
            }
        });

        setTimeout(function() {
            if (!$('.aliexpress-sync-btn').prop('updated-version')) {
                upgradeWarning();
            }
        }, 1000);
    });

    $('#update-unfulfilled-only').on('ifChanged', function (e) {
        if($('.aliexpress-sync-btn').prop('updated-version') &&
            $('#modal-tracking-update').is(':visible')) {
            syncTrackedOrders();
        }
    });

    function upgradeWarning() {
        swal('Upgrade Extension',
            'Please upgrade to a newer version of Dropified Chrome Extension to use this feature.',
            'warning');
    }

    function syncTrackedOrders() {
        var btn = $('.aliexpress-sync-btn');
        var modal = $('#modal-tracking-update');

        btn.button('loading');

        var createdAt = $('input[name="created_at_daterange"]').val();
        if (createdAt.indexOf('all-time') > -1) {
            createdAt = '';
        }

        $.ajax({
            url: api_url('order-fulfill', 'chq'),
            data: {
                store: btn.data('store'),
                all: true,
                unfulfilled_only: $('#update-unfulfilled-only').is(':checked'),
                created_at: createdAt,
                count_only: true
            }
        }).done(function(data) {
            orders = {
                pending: data.pending,
                success: 0,
                error: 0
            };

            $('.pending-orders', modal).text(data.pending + ' ' + 'Order' + (data.pending > 1 ? 's' : ''));

            disable_config_sync = true;

            if (data.pending > 100) {
                if(!$('#update-delay').prop('synced')) {
                    $('#update-delay').val('1');
                }

                if(!$('#update-concurrency').prop('synced')) {
                    $('#update-concurrency').val('1');
                }
            }

            disable_config_sync = false;

            modal.modal({
                backdrop: 'static',
                keyboard: false
            });
        }).fail(function(data) {
            displayAjaxError('Update Orders', data);
        }).always(function() {
            btn.button('reset');
        });
    }

    $('.start-update-btn').click(function(e) {
        var btn = $(this);
        var modal = $('#modal-tracking-update');

        // If orders object isn't filled inside count
        if (!orders.pending) {
            orders = {
                pending: window.syncOrderIds.split(',').length,
                success: 0,
                error: 0
            };
        }

        $('.pending-msg', modal).hide();
        $('.update-progress, .update-progress p', modal).show();
        $('.progress-bar-success', modal).css('width', '0');
        $('.progress-bar-danger', modal).css('width', '0');

        $('#update-unfulfilled-only').prop('disabled', 'disabled');

        btn.hide();
        $('.stop-update-btn').show();

        var createdAt = $('input[name="created_at_daterange"]').val();
        if (createdAt.indexOf('all-time') > -1) {
            createdAt = '';
        }

        $.ajax({
            url: api_url('order-fulfill', 'chq'),
            data: {
                store: btn.data('store'),
                all: true,
                ids: window.syncOrderIds,
                created_at: createdAt,
                unfulfilled_only: $('#update-unfulfilled-only').is(':checked')
            }
        }).done(function(data) {
            updatePromise = P.map(data, checkOrder, {
                concurrency: parseInt($('#update-concurrency').val(), 10).bound(1, 10)
            }).then(function(allValues) {
                updateComplete();
            }).finally(function() {
                if (updatePromise.isCancelled()) {
                    updateComplete();
                }
            });

        }).fail(function(data) {
            displayAjaxError('Update Orders', data);
        });

        window.syncOrderIds = null;
    });

    $('.stop-update-btn').click(function (e) {
        $(this).button('loading');
        updatePromise.cancel();
    });

    $('.refresh-page-btn').click(function (e) {
        $(this).button('loading');
        window.location.reload();
    });

    $('.progress-table').mouseenter(function() {
        if (document.noscrollInterval) {
            clearTimeout(document.noscrollInterval);
            document.noscrollInterval = null;
        }

        $('.progress-table').prop('noscroll', true);
    }).mouseleave(function() {
        document.noscrollInterval = setTimeout(function() {
            $('.progress-table').prop('noscroll', false);
        }, 1000);
    });

    $('#advanced-options-check').on('ifChanged', function (e) {
        $('.advanced-options').toggle(e.target.checked);

        saveConfig('_track_advanced_options', e.target.checked);
    });

    $('#update-delay').on('change', function (e) {
        saveConfig('_track_update_delay', $(e.target).val());
    });

    $('#update-concurrency').on('change', function (e) {
        saveConfig('_track_update_concurrency', $(e.target).val());
    });

    function saveConfig(name, value) {
        if (disable_config_sync) {
            return;
        }

        $.ajax({
            url: api_url('user-config'),
            method: 'POST',
            data: {
                'single': true,
                'name': name,
                'value': value
            }
        });
    }

    function loadConfig() {
        $.ajax({
            url: api_url('user-config'),
            data: {
                'name': '_track_advanced_options,_track_update_delay,_track_update_concurrency',
            }
        }).done(function(data) {
            disable_config_sync = true;

            if(data._track_advanced_options == 'true') {
                $('#advanced-options-check').iCheck('check');
            }

            $('.advanced-options').toggle($('#advanced-options-check')[0].checked);

            if(data._track_update_delay) {
                $('#update-delay').val(data._track_update_delay).prop('synced', true);
            }

            if(data._track_update_concurrency) {
                $('#update-concurrency').val(data._track_update_concurrency).prop('synced', true);
            }

            disable_config_sync = false;
        });
    }

    function checkOrder(order) {
        var delay = parseFloat($('#update-delay').val(), 10).bound(0.1, 100) * 1000;

        if (order.source_type === 'dropified-print') {
            return checkDropifiedPrintOrder(order).then(function(data) {
                // Got Supplier order info
                if (order.source_status == data.details.orderStatus &&
                    order.source_tracking == data.details.tracking_number &&
                    $('#update-unfulfilled-only').is(':checked') &&
                    !order.bundle) {
                    // Order info hasn't changed
                    orders.success += 1;
                    addOrderUpdateItem(order, data.details);
                } else {
                    return updateOrderStatus(order, data.details);
                }
            }).fail(function(data) {
                // Couldn't get Supplier order info
                orders.error += 1;
                addOrderUpdateItem(order, {'error': getAjaxError(data)});
            }).always(function() {
                updateProgress();
            });
        }

        if (order.source_type === 'supplements') {
            return $.ajax({
                url: api_url('sync-order', 'supplements'),
                type: 'POST',
                data: {
                    'store_id': window.store.id,
                    'store_type': window.store.type,
                    'source_id': order.source_id,
                    'track_id': order.id,
                }
            }).then(function(responseData) {
                for (var i = 0, iLength = responseData.orders.length; i < iLength; i++) {
                    var data = responseData.orders[i];
                    // Got Supplier order info
                    if (order.source_status == data.source.orderStatus &&
                        order.source_tracking == data.source.tracking_number &&
                        $('#update-unfulfilled-only').is(':checked') &&
                        !order.bundle) {
                        // Order info hasn't changed
                        orders.success += 1;
                        addOrderUpdateItem(order, data.source);
                    } else {
                        return updateOrderStatus(order, data.source);
                    }
                }
            }).fail(function(data) {
                // Couldn't get Supplier order info
                orders.error += 1;
                addOrderUpdateItem(order, {'error': getAjaxError(data)});

            }).always(function() {
                updateProgress();
            });
        }

        return new P(function(resolve, reject) {
            window.extensionSendMessage({
                subject: 'getOrderStatus',
                order_details: order,
                order: order.source_id,
            }, function(rep) {
                setTimeout(function() {
                    if (rep.hasOwnProperty('error')) {
                        reject({
                            order: order,
                            source: rep
                        });
                    } else {
                        resolve({
                            order: order,
                            source: rep
                        });
                    }
                }, delay);
            });
        }).then(
            function(data) {
                // Got Supplier order info
                if (data.order.source_status == data.source.orderStatus &&
                    data.order.source_tracking == data.source.tracking_number &&
                    $('#update-unfulfilled-only').is(':checked') &&
                    !data.order.bundle) {
                    // Order info hasn't changed
                    orders.success += 1;
                    addOrderUpdateItem(data.order, data.source);
                } else {
                    return updateOrderStatus(data.order, data.source);
                }
            },
            function(data) {
                // Couldn't get Supplier order info
                orders.error += 1;
                addOrderUpdateItem(data.order, data.source);
            }
        ).finally(function() {
            updateProgress();
        });
    }

    function updateOrderStatus(order, source) {
        return $.ajax({
            url: api_url('order-fulfill-update', 'chq'),
            type: 'POST',
            data: {
                'order': order.id,
                'status': source.orderStatus,
                'end_reason': source.endReason,
                'tracking_number': source.tracking_number,
                'order_details': JSON.stringify(source.order_details || {}),
                'bundle': order.bundle,
                'source_id': order.source_id,
            }
        }).done(function(data) {
            orders.success += 1;
            order.updated = true;

            addOrderUpdateItem(order, source);
        }).fail(function(data) {
            source.error = getAjaxError(data);
            addOrderUpdateItem(order, source);
        });
    }

    function addOrderUpdateItem(order, source) {
        if (!$('.progress-table-row').is(':visible')) {
            $('.progress-table-row').show();
        }

        if (source && source.orderStatus && status_map.hasOwnProperty(source.orderStatus)) {
            source.order_status = status_map[source.orderStatus];
        }

        if (order.source_type == 'ebay') {
            order.source_url = 'https://vod.ebay.com/vod/FetchOrderDetails?purchaseOrderId=' + order.source_id;
        } else if (order.source_type == 'supplements') {
            order.source_url = source.source_url;
        } else {
            order.source_url = 'https://trade.aliexpress.com/order_detail.htm?orderId=' + order.source_id;
        }
        var trItem = $(order_update_tpl({
            order: order,
            source: source,
        }));

        $('.progress-table tbody').append(trItem);

        if (!$('.progress-table').prop('noscroll')) {
            trItem[0].scrollIntoView();
        }
    }

    function updateProgress() {
        $('#modal-tracking-update .update-progress .fa-spin').removeClass('fa-spin');

        $('.progress-bar-success').css('width', ((orders.success * 100.0) / orders.pending) + '%')
            .text(orders.success + ' order' + (orders.success > 1 ? 's' : ''));

        $('.progress-bar-danger').css('width', ((orders.error * 100.0) / orders.pending) + '%')
            .text(orders.error + ' order' + (orders.error > 1 ? 's' : ''));
    }

    function updateComplete() {
        $('.update-progress .progress').removeClass('active').removeClass('progress-striped');
        $('.update-progress p').text('Update Completed, refresh the page to view the updates.');
        $('.stop-update-btn').hide();
        $('.refresh-page-btn').show();
    }

    setupDateRangePicker('#created_at_daterange', 'input[name="created_at_daterange"]');
    setupDateRangePicker('#date', 'input[name="date"]');

    $('#created_at_daterange').data('daterangepicker').setStartDate(moment().subtract(30, 'days').format('MM/DD/YYYY'));
    $('#created_at_daterange').data('daterangepicker').setEndDate(moment().format('MM/DD/YYYY'));
    $('#created_at_daterange').trigger('apply.daterangepicker', $('#created_at_daterange').data('daterangepicker'));
    $('input[name="created_at_daterange"]').on('change', syncTrackedOrders);

    $('#advanced-options-check').iCheck('uncheck');

    $(function () {
        setTimeout(loadConfig, 500);
    });
})();
