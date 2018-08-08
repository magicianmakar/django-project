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

    $('#update-unfulfilled-only').on('change', function (e) {
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

        window.extensionSendMessage({
            subject: 'AliexpessAccount',
        }, function(rep) {
            if (rep && rep.name) {
                $('.aliexpress-account').html(' - Update using <b>' + rep.name + '</b> Aliexpress Account.').show();
            } else {
                $('.aliexpress-account').hide();
            }
        });

        $.ajax({
            url: api_url('order-fulfill', 'gear'),
            data: {
                store: btn.data('store'),
                all: true,
                unfulfilled_only: $('#update-unfulfilled-only').is(':checked'),
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

        $('.pending-msg', modal).hide();
        $('.update-progress, .update-progress p', modal).show();
        $('.progress-bar-success', modal).css('width', '0');
        $('.progress-bar-danger', modal).css('width', '0');

        $('#update-unfulfilled-only').prop('disabled', 'disabled');

        btn.hide();
        $('.stop-update-btn').show();

        $.ajax({
            url: api_url('order-fulfill', 'gear'),
            data: {
                store: btn.data('store'),
                all: true,
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

    $('#advanced-options-check').on('change', function (e) {
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
                $('#advanced-options-check').prop('checked', true).trigger('change');
            }

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

        return new P(function(resolve, reject) {
            window.extensionSendMessage({
                subject: 'getOrderStatus',
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
                // Got Aliexpress order info
                if (data.order.source_status == data.source.orderStatus &&
                    data.order.source_tracking == data.source.tracking_number &&
                    $('#update-unfulfilled-only').is(':checked')) {
                    // Order info hasn't changed
                    orders.success += 1;
                    addOrderUpdateItem(data.order, data.source);
                } else {
                    return updateOrderStatus(data.order, data.source);
                }
            },
            function(data) {
                // Couldn't get Aliexpress order info
                orders.error += 1;
                addOrderUpdateItem(data.order, data.source);
            }
        ).finally(function() {
            updateProgress();
        });
    }

    function updateOrderStatus(order, source) {
        return $.ajax({
            url: api_url('order-fulfill-update', 'gear'),
            type: 'POST',
            data: {
                'order': order.id,
                'status': source.orderStatus,
                'end_reason': source.endReason,
                'tracking_number': source.tracking_number,
                'order_details': JSON.stringify(source.order_details || {}),
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

    $(function () {
        setTimeout(loadConfig, 500);
    });

})();