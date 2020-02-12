(function () {
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

            line.find('.pay-for-product').hide();
            line.find('.line-checkbox').attr('checked', false).attr('disabled', true);
        }
    }

    function makePayment (orderDataIds) {
        var lenOrders = orderDataIds.length;

        if (!lenOrders) {
            toastr.warning("Please select orders for processing.");
            return;
        }

        var msg = "Preparing to pay for " + lenOrders + " ";
        msg += makePlural('item', lenOrders);
        msg += ".";

        toastr.info(msg);

        var url = api_url('make-payment', 'product_common');
        data = {'order_data_ids': orderDataIds};
        $.post(url, JSON.stringify(data), {
            contentType: 'applicaton/json'
        }).done(function (data) {
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
        });
    }

    $(document).ready(function () {
        'use strict';

        $(".pay-for-product").click(function () {
            var orderDataId = $(this).parent().attr('order-data-id');
            makePayment([orderDataId]);
        });

        $(".pay-selected-lines").click(function () {
            var orderDataIds = [];
            $('.line-checkbox:checkbox:checked').each(function (i, item) {
                var line = $(item).parents('.line');
                if (line.attr("is-pls") === "true") {
                    orderDataIds.push(line.attr('order-data-id'));
                }
            });
            makePayment(orderDataIds);
        });
    });
}());
