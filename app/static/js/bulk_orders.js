var bulkOptions = $('#bulk-order-btn').parent().find('.dropdown-menu li');

if (bulkOptions.length === 1) {
    $('#bulk-order-btn').addClass('bulk-order-btn').data('source', bulkOptions.find('a').data('source'));
    $('#bulk-order-btn .caret').remove();
    $('#bulk-order-btn .dropdown-menu').remove();
}

function bulkAddOrderToQueue(order) {
    if (!window.extensionSendMessage) {
        swal('Please reload the page and make sure you are using the latest version of the extension.');
        return;
    }

    window.extensionSendMessage({
        subject: 'AddOrderToQueue',
        from: 'website',
        order: order
    });
}

function addOrdersToPrivateLabel(orders) {
    var orderDataIDs = [];
    for (var i = 0, iLength = orders.length; i < iLength; i++) {
        var bulkItems = orders[i].items;
        if (bulkItems) {
            for (var y = 0, yLength = bulkItems.length; y < yLength; y++) {
                orderDataIDs.push(bulkItems[y].order_data);
            }
        } else {
            orderDataIDs.push(window.bulkOrderQueue.data[i].order_data);
        }
    }
    processOrders(orderDataIDs, false);
}

function addOrdersToAlibaba(orders) {
    var orderDataIDs = [];
    for (var i = 0, iLength = orders.length; i < iLength; i++) {
        var bulkItems = orders[i].items;
        if (bulkItems) {
            for (var y = 0, yLength = bulkItems.length; y < yLength; y++) {
                orderDataIDs.push(bulkItems[y].order_data);
            }
        } else {
            orderDataIDs.push(window.bulkOrderQueue.data[i].order_data);
        }
    }
    orderItemsAlibaba(orderDataIDs);
}

window.bulkOrderQueue = null;
function fetchOrdersToQueue(data, page_count) {
    page_count = typeof (page_count) === 'undefined' ? 0 : page_count;

    $('.stop-bulk-btn').show()
        .button('reset')
        .removeClass('btn-primary')
        .addClass('btn-danger');

    var api_url = /^http/.test(data) ? data : cleanUrlPatch(window.location.href);
    var api_data = /^http/.test(data) ? null : data;
    $.ajax({
        url: api_url,
        type: 'GET',
        data: api_data,
        success: function(data) {
            page_count += 1;

            var pbar = $('#bulk-order-modal .progress .progress-bar');
            var page = page_count;
            var pmax = parseInt(pbar.attr('max'));
            pbar.css('width', ((page * 100.0) / pmax) + '%')
                .text(page + ' Page' + (page > 1 ? 's' : ''))
                .attr('current', page);

            $.each(data.orders, function (i, order) {
                window.bulkOrderQueue.data.push(order);
            });

            window.bulkOrderQueue.next = data.next;
            if (data.next && !window.bulkOrderQueue.stop && page_count < pmax) {
                fetchOrdersToQueue(data.next, page_count);
            } else if (!data.next || page_count >= pmax) {
                $('.stop-bulk-btn').hide();
                $("#bulk-order-steps").steps('next');
            } else {
                $('.stop-bulk-btn')
                    .button('continue')
                    .removeClass('btn-danger')
                    .addClass('btn-primary');

                var currentStep = $("#bulk-order-steps").steps('getCurrentIndex');
                if (currentStep == 1) {  // Still at progress bar step
                    $("#bulk-order-steps").steps('next');
                }
            }
        },
        error: function(data) {
            displayAjaxError('Bulk Order Processing', data);

            window.bulkOrderQueue.stop = true;
            $('.stop-bulk-btn').button('continue')
                .removeClass('btn-danger').addClass('btn-primary');
        }
    });
}

$('#bulk-order-button-wrapper').on('click', '.bulk-order-btn', function (e) {
    e.preventDefault();

    var orders_count = parseInt($('#bulk-order-btn').attr('orders-count'));
    if (!orders_count) {
        swal({
            title: 'No orders found',
            text: 'Try adjusting your current Filters',
            type: "warning",
        });

        return;
    }

    var source = $(this).data('source');
    var bulkModal = $('#bulk-order-modal');

    var isPrintOnDemand = source === 'print-on-demand';
    bulkModal.data('dropified-print', isPrintOnDemand);

    var isPrivateLabel = source === 'private-label';
    bulkModal.data('dropified-supplements', isPrivateLabel);

    var isAlibaba = source === 'alibaba';
    bulkModal.data('alibaba', isAlibaba);

    if (window.bulkOrderQueue && window.bulkOrderQueue.data.length) {
        if (isPrivateLabel && window.bulkOrderQueue.is_supplement_bulk_order) {
            addOrdersToPrivateLabel(window.bulkOrderQueue.data);
            $('#modal-order-detail').modal('show');
            return true;
        }

        if (isAlibaba && window.bulkOrderQueue.is_alibaba_bulk_order) {
            addOrdersToAlibaba(window.bulkOrderQueue.data);
            $('#modal-alibaba-order-detail').modal('show');
            return true;
        }
    }

    window.bulkOrderQueue = {
        pages: {},
        data: [],
        stop: false,
        next: null,
        is_dropified_print: isPrintOnDemand,
        is_supplement_bulk_order: isPrivateLabel,
        is_alibaba_bulk_order: isAlibaba,
    };

    var is_dropified_print = window.bulkOrderQueue.is_dropified_print;
    $('#bulk-order-modal .modal-title .original-title').toggleClass('hidden', is_dropified_print);
    $('#bulk-order-modal .modal-title .dropified-print-title').toggleClass('hidden', !is_dropified_print);

    bulkModal.modal({
        backdrop: 'static',
        keyboard: false
    });

    $('.bulk-order-step [name="queue_page_from"]').trigger('focus');

    startBulkOrderSteps();

    ga('clientTracker.send', 'event', 'Bulk Order', 'Shopify', sub_conf.shop);
});

$('#bulk-order-modal').on('click', '.stop-bulk-btn', function (e) {
    e.preventDefault();

    if (window.bulkOrderQueue.stop == true && window.bulkOrderQueue.next) {
        $(e.target).button('reset').removeClass('btn-danger').addClass('btn-primary');
        window.bulkOrderQueue.stop = false;
        fetchOrdersToQueue(window.bulkOrderQueue.next);
    } else {
        window.bulkOrderQueue.stop = true;
        $(e.target).button('loading');
    }

    ga('clientTracker.send', 'event', 'Stop Bulk Order', 'Shopify', sub_conf.shop);
});

function startBulkOrderSteps() {
    $("#bulk-order-steps > div").addClass('bulk-order-step');

    $("#bulk-order-steps").steps({
        bodyTag: "div.bulk-order-step",
        enableAllSteps: false,
        forceMoveForward: true,
        labels: {
            finish: "Start ordering",
        },
        onStepChanging: function (event, currentIndex, newIndex) {
            // Always allow going backward
            if (currentIndex > newIndex) {
                return true;
            }

            if (currentIndex == 0) {
                var pageFrom = parseInt($('[name="queue_page_from"]').val());
                var pageTo = parseInt($('[name="queue_page_to"]').val());
                var maxPages = 100;

                if (isNaN(pageFrom) || isNaN(pageTo)) {
                    $('#bulk-order-step-error').css('display', '');
                    $('#bulk-order-step-error span').text('Page range is not a number');

                    return false;
                } else if (pageFrom < 1 || pageTo > maxPages) {
                    $('#bulk-order-step-error').css('display', '');
                    $('#bulk-order-step-error span').text('Page numbers outside of range 1-' + maxPages);

                    return false;
                } else if (pageFrom > pageTo) {
                    $('#bulk-order-step-error').css('display', '');
                    $('#bulk-order-step-error span').text('Starting page number must be higher than ending');

                    return false;
                } else {
                    $('#bulk-order-step-error').css('display', 'none');
                    $('#bulk-order-step-error span').text('');
                    window.bulkOrderQueue = $.extend(true, window.bulkOrderQueue, {
                        pages: {
                            'from': pageFrom,
                            'to': pageTo
                        },
                        data: [],
                        stop: false,
                        next: null,
                    });
                }
            }

            return true;
        },
        onStepChanged: function (event, currentIndex, priorIndex) {
            if (currentIndex == 0) {
                // Stop progress if we go back to one
                window.bulkOrderQueue.stop = true;

            } else if (currentIndex == 1 && priorIndex == 0) {  // Coming from "Select Pages" step
                window.bulkOrderQueue.stop = false;
                window.bulkOrderQueue.data = [];

                var maxPages = window.bulkOrderQueue.pages.to - window.bulkOrderQueue.pages.from + 1;
                $('#bulk-order-modal .progress .progress-bar')
                    .css('width', '0px')
                    .attr('max', maxPages)
                    .attr('current', '0');

                var formData = $('form.filter-form').serializeArray();
                formData.push({name: 'bulk_queue', value: '1'});
                formData.push({name: 'page_start', value: window.bulkOrderQueue.pages.from});
                formData.push({name: 'page_end', value: window.bulkOrderQueue.pages.to});
                if (window.bulkOrderQueue.is_supplement_bulk_order) {
                    formData.push({name: 'is_supplement_bulk_order', value: '1'});
                } else if (window.bulkOrderQueue.is_alibaba_bulk_order) {
                    formData.push({name: 'single_supplier', value: 'alibaba'});
                } else if (window.bulkOrderQueue.is_dropified_print) {
                    formData.push({name: 'is_dropified_print', value: '1'});
                }

                fetchOrdersToQueue(formData);
            } else if (currentIndex == 2) {
                var queueOrdersLength = window.bulkOrderQueue.data.length;

                if (queueOrdersLength == 0) {
                    $('#bulk-order-count').text('No Orders');
                } else if (queueOrdersLength == 1) {
                    $('#bulk-order-count').text('1 Order');
                } else if (queueOrdersLength > 1) {
                    $('#bulk-order-count').text(queueOrdersLength + ' Orders');
                }
            }
        },
        onFinished: function (event, currentIndex) {
            if (window.bulkOrderQueue.is_dropified_print) {
                addOrdersToPrint(window.bulkOrderQueue.data);
            } else if (window.bulkOrderQueue.is_supplement_bulk_order) {
                addOrdersToPrivateLabel(window.bulkOrderQueue.data);
            } else if (window.bulkOrderQueue.is_alibaba_bulk_order) {
                addOrdersToAlibaba(window.bulkOrderQueue.data);
            } else {
                $.each(window.bulkOrderQueue.data, function (i, order) {
                    bulkAddOrderToQueue(order);
                });
            }

            $('#bulk-order-modal').modal('hide');
            $("#bulk-order-steps").steps('destroy');
        }
    });
}
