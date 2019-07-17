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

window.bulkOrderQueue = null;
function fetchOrdersToQueue(data) {
    $('.stop-bulk-btn').show();
    $('.stop-bulk-btn').button('reset').removeClass('btn-primary').addClass('btn-danger');

    var api_url = /^http/.test(data) ? data : cleanUrlPatch(window.location.href);
    var api_data = /^http/.test(data) ? null : data;
    $.ajax({
        url: api_url,
        type: 'GET',
        data: api_data,
        success: function(data) {
            var pbar = $('#bulk-order-modal .progress .progress-bar');
            var page = parseInt(pbar.attr('current')) + 1;
            var pmax = parseInt(pbar.attr('max'));
            pbar.css('width', ((page * 100.0) / pmax) + '%')
                .text(page + ' Page' + (page > 1 ? 's' : ''))
                .attr('current', page);

            $.each(data.orders, function (i, order) {
                window.bulkOrderQueue.data.push(order);
            });

            window.bulkOrderQueue.next = data.next;
            if (data.next && !window.bulkOrderQueue.stop) {
                fetchOrdersToQueue(data.next);
            } else if (!data.next) {
                $('.stop-bulk-btn').hide();
                $("#bulk-order-steps").steps('next');
            } else {
                $('.stop-bulk-btn').button('continue');
                $('.stop-bulk-btn').removeClass('btn-danger').addClass('btn-primary');

                var currentStep = $("#bulk-order-steps").steps('getCurrentIndex');
                if (currentStep == 1) {  // Still at progress bar step
                    $("#bulk-order-steps").steps('next');
                }
            }
        },
        error: function(data) {
            displayAjaxError('Bulk Order Processing', data);

            window.bulkOrderQueue.stop = true;
            $('.stop-bulk-btn').button('continue');
            $('.stop-bulk-btn').removeClass('btn-danger').addClass('btn-primary');
        }
    });
}

$('.bulk-order-btn').click(function (e) {
    e.preventDefault();

    var orders_count = parseInt($(e.target).attr('orders-count'));
    if (!orders_count) {
        swal({
            title: 'No orders found',
            text: 'Try adjusting your current Filters',
            type: "warning",
        });

        return;
    }

    ga('clientTracker.send', 'event', 'Bulk Order', 'Shopify', sub_conf.shop);

    window.bulkOrderQueue = {
        pages: {},
        data: [],
        stop: false,
        next: null
    };

    $('#bulk-order-modal').modal({
        backdrop: 'static',
        keyboard: false
    });
});

$('#bulk-order-modal').on('click', '.stop-bulk-btn', function (e) {
    e.preventDefault();

    ga('clientTracker.send', 'event', 'Stop Bulk Order', 'Shopify', sub_conf.shop);

    if (window.bulkOrderQueue.stop == true && window.bulkOrderQueue.next) {
        $(e.target).button('reset').removeClass('btn-danger').addClass('btn-primary');
        window.bulkOrderQueue.stop = false;
        fetchOrdersToQueue(window.bulkOrderQueue.next);
    } else {
        window.bulkOrderQueue.stop = true;
        $(e.target).button('loading');
    }
});

$("#bulk-order-steps").steps({
    bodyTag: "div.bulk-order-step",
    enableAllSteps: false,
    forceMoveForward: true,
    labels: {
        finish: "Start ordering",
    },
    onStepChanging: function(event, currentIndex, newIndex) {
        // Always allow going backward
        if (currentIndex > newIndex) {
            return true;
        }

        if (currentIndex == 0) {
            var pageFrom = parseInt($('[name="queue_page_from"]').val());
            var pageTo = parseInt($('[name="queue_page_to"]').val());
            var maxPages = parseInt($('.bulk-order-btn').attr('pages-count'));

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
                window.bulkOrderQueue = {
                    pages: {
                        'from': pageFrom,
                        'to': pageTo
                    },
                    data: [],
                    stop: false,
                    next: null
                };
            }
        } else if (currentIndex == 1) {
            var progress = $('#bulk-order-modal .progress .progress-bar');
            var progressMax = parseInt(progress.attr('max'));
            var progressCurrent = parseInt(progress.attr('current'));

            if (progressMax == progressCurrent || window.bulkOrderQueue.stop) {
                $('#bulk-order-load-error').css('display', 'none');
            } else {
                $('#bulk-order-load-error').css('display', '');
                return false;
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
            $('#bulk-order-modal .progress .progress-bar').css('width', '0px');
            $('#bulk-order-modal .progress .progress-bar').attr('max', maxPages);
            $('#bulk-order-modal .progress .progress-bar').attr('current', '0');

            var formData = $('form.filter-form').serializeArray();
            formData.push({name: 'bulk_queue', value: '1'});
            formData.push({name: 'page_start', value: window.bulkOrderQueue.pages.from});
            formData.push({name: 'page_end', value: window.bulkOrderQueue.pages.to});

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
        $.each(window.bulkOrderQueue.data, function (i, order) {
            bulkAddOrderToQueue(order);
        });

        $('#bulk-order-modal').modal('hide');
    }
});
