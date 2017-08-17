var shopify_send_tpl;
function initializeShopifySendModal(btn) {
    $('#modal-shopify-send .progress').show();
    $('#modal-shopify-send input, #modal-shopify-send select').prop('disabled', true);
    $('#modal-shopify-send').prop('total_sent_success', 0);
    $('#modal-shopify-send').prop('total_sent_error', 0);
}

function setShopifySendModalProgress(count, item, req_success, data) {
    var total_sent_success = parseInt($('#modal-shopify-send').prop('total_sent_success'));
    var total_sent_error = parseInt($('#modal-shopify-send').prop('total_sent_error'));

    var success = req_success && 'product' in data;
    var status;
    var product_title = item.element.attr('product-title');
    if (success) {
        total_sent_success += 1;
        var chk_el = item.element.find('input.item-select[type=checkbox]');
        chk_el.iCheck('uncheck');
        // chk_el.parents('td').html('<span class="label label-success">Sent</span>');
        status = 'Success';
    } else {
        total_sent_error += 1;
        if (data.responseJSON && typeof (data.responseJSON.error) == 'string') {
            status = data.responseJSON.error;
        }
    }

    if (!$('.progress-table-row').is(':visible')) {
        $('.progress-table-row').show();
    }
    var trItem = $(shopify_send_tpl({
        product: { id: item.product, title: product_title },
        success: success,
        status: status,
    }));
    $('.progress-table tbody').append(trItem);
    if (!$('.progress-table').prop('noscroll')) {
        trItem[0].scrollIntoView();
    }

    $('#modal-shopify-send').prop('total_sent_success', total_sent_success);
    $('#modal-shopify-send').prop('total_sent_error', total_sent_error);

    $('#modal-shopify-send .progress-bar-success').css('width', ((total_sent_success * 100.0) / count) + '%');
    $('#modal-shopify-send .progress-bar-danger').css('width', ((total_sent_error * 100.0) / count) + '%');

    if ((total_sent_success + total_sent_error) == count) {
        $('#modal-shopify-send .progress').removeClass('progress-striped active');
        $('#modal-shopify-send .modal-footer').hide();
    }
}

$(function() {
    shopify_send_tpl = Handlebars.compile($("#product-send-template").html());
    $('#modal-shopify-send').on('shown.bs.modal', function() {
        $('.progress-table-row').hide();
        $('.progress-table tbody').html('');
        $('#modal-shopify-send .progress').hide();
        $('#modal-shopify-send .progress').addClass('progress-striped active');
        $('#modal-shopify-send .modal-footer').show();
        $('#modal-shopify-send input, #modal-shopify-send select').prop('disabled', false);
        $('#modal-shopify-send #shopify-send-btn').button('reset');

        $('#modal-shopify-send .progress-bar-success').css('width', '0');
        $('#modal-shopify-send .progress-bar-danger').css('width', '0');
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
});