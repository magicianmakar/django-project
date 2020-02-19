function saveForLater(storeType, storeId, callback) {
    var data = {
        store: storeId,
        data: JSON.stringify(apiData),
        b: true
    };

    var url = api_url('save-for-later', 'shopify');
    if (storeType !== 'shopify') {
        url = api_url('product-save', storeType);
    }

    $.ajax({
        url: url,
        type: 'POST',
        data: JSON.stringify(data),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        success: function (data) {
            if (callback) {
                callback(data, true);
            }
        },
        error: function (data) {
            if (callback) {
                callback(data, false);
            }
        }
    });
}

function getPostExportPusherHandler(productId) {
    return function(data) {
        var pusher = new Pusher(data.pusher.key);
        var channel_hash = data.pusher.channel;
        var channel = pusher.subscribe(channel_hash);

        channel.bind('product-export', function(data) {
            if (data.product == productId) {
                var btn = $('#id_send_to_store_confirm');
                if (data.progress) {
                    btn.text(data.progress);
                    return;
                }

                pusher.unsubscribe(channel_hash);

                if (data.success) {
                    btn.button('reset');
                    toastr.success("Product successfully exported", "Product Export");
                    $('#modal-send-to-store').find('.close').trigger('click');
                } else {
                    displayAjaxError('Product Export', data);
                }
            }
        });
    };
}

function sendToStore(storeType, storeId, publish) {
    saveForLater(storeType, storeId, function(data, result) {
        if (result === true) {
            var productId = data.product.id;
            var jsXHR;
            if (storeType === 'shopify') {
                sendProductToShopify(apiData, storeId, productId, function (data) {
                    $('#id_send_to_store_confirm').button('reset');
                    toastr.success("Product successfully exported", "Export");
                    $('#modal-send-to-store').find('.close').trigger('click');
                });
            } else {
                if (storeType === 'chq') {
                    jqXHR = sendProductToCommerceHQ(productId, storeId, publish);
                    jqXHR.done(getPostExportPusherHandler(productId));
                } else if (storeType === 'gkart') {
                    jqXHR = sendProductToGrooveKart(productId, storeId, publish);
                    jqXHR.done(getPostExportPusherHandler(productId));
                } else if (storeType === 'woo') {
                    jqXHR = sendProductToWooCommerce(productId, storeId, publish);
                    jqXHR.done(getPostExportPusherHandler(productId));
                }
            }
        }
    });
}

$(document).ready(function(){
    $("#send_to_store").click(function() {
        $('#modal-send-to-store').modal({backdrop: 'static', keyboard: false});
    });

    $("#id_store_type").change(function() {
        var val = $(this).val();
        var stores = storeData[val];

        $('#id_store_list').find('option').remove().end();
        for (var i=0; i<stores.length; i++) {
            var id = stores[i].id;
            var value = stores[i].value;
            $('#id_store_list').append(
                $("<option value='" + id + "'>" + value + "</option>")
            );
        }
    });

    $("#id_store_type").trigger('change');

    $("#id_send_to_store_confirm").click(function() {
        var storeType = $("#id_store_type").val();
        var storeId = $('#id_store_list').val();
        var publish = $('#send-product-visible').prop('checked') || false;
        $(this).button('loading');
        sendToStore(storeType, storeId, publish);
    });
});
