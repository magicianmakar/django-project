function getCorrectRef(btn, text) {
    if($.fn.hasOwnProperty('bootstrapBtn')) {
        btn.bootstrapBtn(text);
    } else {
        btn.button(text);
    }

}

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
                    getCorrectRef(btn, 'reset');
                    toastr.success("Product successfully exported", "Product Export");
                    $('#modal-send-to-store').find('.close').trigger('click');
                    redirectToMySupplements();
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
            var jqXHR;
            if (storeType === 'shopify') {
                sendProductToShopify(apiData, storeId, productId, function (data) {
                    getCorrectRef($('#id_send_to_store_confirm'), 'reset');
                    toastr.success("Product successfully exported", "Export");
                    $('#modal-send-to-store').find('.close').trigger('click');
                    redirectToMySupplements();
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
                } else if (storeType === 'bigcommerce') {
                    jqXHR = sendProductToBigCommerce(productId, storeId, publish);
                    jqXHR.done(getPostExportPusherHandler(productId));
                } else {
                    getCorrectRef($('#id_send_to_store_confirm'), 'reset');
                    var store = 'eBay';
                    if (storeType == 'fb') {
                        store = 'Facebook';
                    }
                    else if (storeType == 'google') {
                        store = 'Google';
                    }
                                        
                    var link = app_base_link + '/' + storeType + '/products?store=n';
                    var msg = "In order to send this product to " + store + ", You need to add some required fields.<br>";
                    msg = msg + "Click to see <a href='"+ link +"'>the saved product</a>";
                    swal({
                        title: 'Product saved to Non Connected',
                        text: msg,
                        type: 'success',
                        html: true,
                    });
                }
            }
        }
    });
}

function sendSampleLabelToStore(storeType, storeId, publish) {
    var form = document.getElementById('user_supplement_form');
    form.action.value = 'preapproved';
    form.upload_url.value = $('#sample_label').attr('data-label-url');
    form.add_to_basket.value = '1';
    var url = $('#sample_label').attr('data-post-url');
    $.ajax({
        url: url,
        data: $('form#user_supplement_form').serialize(),
        type: 'post',
        dataType: 'json',
        success: function(res) {
            window.apiData = JSON.parse(res.data);
            // adding to basket
            sendToBasket(window.apiData.user_supplement_id);
        },
        error: function(xhr, status, error) {
            var errorMessage = xhr.status + ': ' + xhr.statusText;
            getCorrectRef($('#id_send_to_store_confirm'), 'reset');
            toastr.error("An error occured", "Export");
            $('#modal-send-to-store').find('.close').trigger('click');
            $('#sample_label').attr('data-send-to-store', 'false');

        }
    });
}

function sendToBasket(product_id){

    var data = {'product-id': product_id};

    var url = api_url('add_basket', 'supplements');
    $.ajax({
        url: url,
        type: "POST",
        data: JSON.stringify(data),
        dataType: 'json',
        contentType: 'application/json',
        success: function (response) {
           toastr.success("Item added to your <a href='#'>Basket</a>");
           window.location = app_link('supplements/basket');
        },
        error: function (response) {
           toastr.error("Error adding item to your <a href='#'>Basket</a>");
        },
    });

}

function redirectToMySupplements() {
    if(typeof $('#sample_label').attr('data-send-to-store') !== 'undefined') {
        if ($('#sample_label').attr('data-send-to-store') === 'true') {
            $('#sample_label').attr('data-send-to-store', 'false');
            window.location.href = $('#sample_label').attr('data-redirect-url');
        }
    }
}

$(document).ready(function(){
    $("#send_to_store").click(function() {
        $('#modal-send-to-store').modal({backdrop: 'static', keyboard: false});
    });

    $("#id_store_type").change(function() {
        var val = $(this).val() || 'shopify';
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
        getCorrectRef($(this), 'loading');
        if ($('#sample_label').attr('data-send-to-store') === 'true') {
            sendSampleLabelToStore(storeType, storeId, publish);
        }
        else {
            sendToStore(storeType, storeId, publish);
        }
    });
});
