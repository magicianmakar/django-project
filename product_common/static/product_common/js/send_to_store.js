function saveForLater(storeType, storeId, callback) {
    var data = {
        store: storeId,
        data: JSON.stringify(apiData),
        b: true
    };

    var url = '/api/shopify/save-for-later';
    if (storeType === 'chq') {
        url = '/api/chq/product-save';
    } else if (storeType === 'gkart') {
        url = '/api/gkart/product-save';
    } else if (storeType === 'woo') {
        url = '/api/woo/product-save';
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

function sendToStore(storeType, storeId, publish) {
    saveForLater(storeType, storeId, function(data, result) {
        if (result === true) {
            var productId = data.product.id;
            if (storeType === 'shopify') {
                sendProductToShopify(apiData, storeId, productId, function (data) {
                    $('#id_send_to_store_confirm').button('reset');
                    toastr.success("Product successfully exported", "Export");
                    $('#modal-send-to-store').find('.close').trigger('click');
                });
            } else {
                if (storeType === 'chq') {
                    sendProductToCommerceHQ(productId, storeId, publish);
                } else if (storeType === 'gkart') {
                    sendProductToGrooveKart(productId, storeId, publish);
                } else if (storeType === 'woo') {
                    sendProductToWooCommerce(productId, storeId, publish);
                }
                $('#id_send_to_store_confirm').button('reset');
                toastr.success("Product successfully exported", "Export");
                $('#modal-send-to-store').find('.close').trigger('click');
            }
        }
    });
}

function getModal(current) {
    return $(current).parents('.export-product-modal');
}

$(document).ready(function(){
    $("#send_to_store").click(function() {
        $('#modal-send-to-store').modal({backdrop: 'static', keyboard: false});
    });

    $("#save_for_later").click(function () {
        $('#modal-save-for-later').modal({backdrop: 'static', keyboard: false});
    });

    $(".export-product-modal .store-type").change(function() {
        var val = $(this).val();
        var stores = storeData[val];

        getModal(this).find('.store-list').find('option').remove().end();
        for (var i=0; i<stores.length; i++) {
            var id = stores[i].id;
            var value = stores[i].value;
            getModal(this).find('.store-list').append(
                $("<option value='" + id + "'>" + value + "</option>")
            );
        }
    }).trigger('change');

    $(".export-product-modal .submit").click(function() {
        var storeType = getModal(this).find('.store-type').val();
        var storeId = getModal(this).find('.store-list').val();
        var publish = getModal(this).find('.send-product-visible').prop('checked');
        publish = publish || false;

        var submitBtn = this;
        $(submitBtn).button('loading');

        if (getModal(this).data('type') === 'send') {
            sendToStore(storeType, storeId, publish);
        } else {
            saveForLater(storeType, storeId, function (data, result) {
                if (result === true) {
                    toastr.success("Product successfully saved", "Save for Later");
                    $('#modal-save-for-later').find('.close').trigger('click');
                } else {
                    toastr.error("Failed to save product", "Save for Later");
                }
                $(submitBtn).button('reset');
            });
        }
    });
});
