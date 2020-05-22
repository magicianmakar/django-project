$(".tag-it").tagit({
    allowSpaces: true,
    autocomplete: {
        source: '/autocomplete/tags',
        delay: 500,
        minLength: 1
    }
});

function updatePrice() {
    var from = $('[name="ships_from"]').val();
    var cost = costBySku[from];
    if (cost && cost.cost) {
        $('#price .form-control').text(cost.cost);
        $('#suggested_price .form-control').text(cost.suggested_price);
        $('[name="price"]').val(cost.price);
        $('[name="compare_at_price"]').val(cost.compare_at);
    }
}
updatePrice();
$('[name="ships_from"]').on('change', updatePrice);

function saveImages() {
    var images = [];
    for (var i = 0, iLength = customImages.length; i < iLength; i++) {
        images.push(customImages[i].src);
    }
    $('[name="images"]').val(JSON.stringify(images));
}
function loadImages() {
    $.each(customImages, function(key, image) {
        if ($('.image[data-position="' + image.position + '"]').length === 0) {
            var imageTemplate = Handlebars.compile($("#image").html());
            $('#images').append(imageTemplate(image));
        }
    });
    saveImages();
}
function addImages(images) {
    var lastPosition = $('#images .image:last');
    lastPosition = lastPosition.length > 0 ? parseInt(lastPosition.data('position')) : 0;

    images = $.map(images, function(image) {
        lastPosition += 1;
        return {'src': image, 'position': lastPosition};
    });
    customImages = customImages.concat(images);
    loadImages();
}
$('#images').on('click', '.delete-image', function(e) {
    e.preventDefault();
    var image = $(this).parents('.image');
    var position = image.data('position');

    image.remove();
    customImages = $.map(customImages, function(image) {
        if (image.position != position) {
            return image;
        }
    });
    saveImages();
});
loadImages();

var imagesUploader = new plupload.Uploader({
    runtimes: 'html5',
    browse_button: 'add-images',
    container: document.getElementById('add-images-wrapper'),

    url: window.plupload_Config.url,
    file_name_name: false,
    multipart: true,
    multipart_params: {
        filename: 'filename',
        utf8: true,
        AWSAccessKeyId: window.plupload_Config.AWSAccessKeyId,
        acl: "public-read",
        policy: window.plupload_Config.policy,
        signature: window.plupload_Config.signature,
        key: window.plupload_Config.key,
        'Content-Type': 'image/jpeg',
    },
    filters: {
        max_file_size: '100mb',
        mime_types: [
            {'title': "Image files", 'extensions': "jpg,jpeg"}
        ]
    },
    init: {
        BeforeUpload: function(up, file) {
            var params = up.settings.multipart_params;
            params['Content-Type'] = file.type;

            var randomPrefix = (window.crypto.getRandomValues(new Uint32Array(1))[0]).toString(16);
            var ext = file.name.split('.').pop();
            var name = randomPrefix + '_customimage.' + ext;
            params.key = window.plupload_Config.paramsKey + name;
        },
        FilesAdded: function(up, files) {
            imagesUploader.start();
            $('#add-images').bootstrapBtn('loading');
        },
        UploadProgress: function(up, file) {
            $('#add-images').text('Uploading ' + file.name + ' (' + file.percent + '%)');
        },
        FileUploaded: function(up, file, info) {
            var key = up.settings.multipart_params.key;
            var url = window.plupload_Config.uploadedUrl + key;
            addImages([url]);
        },
        UploadComplete: function(up, files) {
            $('#add-images').bootstrapBtn('reset');
        }
    }
});
imagesUploader.init();

function sendProductToShopify(product, store_id, product_id, callback, callback_data) {
    var api_data = {
      "product": {
        "title": product.title,
        "body_html": product.description,
        "product_type": product.type,
        "vendor": product.vendor,
        "published": true,
        "tags": product.tags,
        "variants": [],
        "options": [],
        "images" :[]
      }
    };

    api_data.product.images = $.map(product.images, function(i, k) {
        var image = {
            src: i
        };

        var imageFileName = hashUrlFileName(image.src);
        if (product.variants_images && product.variants_images.hasOwnProperty(imageFileName)) {
            image.filename = 'v-'+hashText(product.variants_images[imageFileName])+'__'+imageFileName;
        }

        return image;
    });

    api_data.product.options = $.map(product.variants, function(v, k) {
        return {
            'name': v.title,
            'values': v.values
        };
    });

    api_data.product.variants = $.map(product.variants_info, function(info, k) {
        var variant_data = {
            price: info.price,
            compare_at_price: info.compare_at,
            sku: info.sku
        };

        var titles = info.title.split(' / ');
        var options = ['option1', 'option2', 'option3'];
        $.each(titles, function(k, title) {
            var option = options.shift();
            variant_data[option] = title;
        });

        variant_data.title = titles.join(' & ');
        return variant_data;
    });

    $.ajax({
        url: '/api/shopify',
        type: 'POST',
        data: JSON.stringify ({
            'product': product_id,
            'store': store_id,
            'data': JSON.stringify(api_data),
            'b': true,
        }),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        success: function (data) {
             if (data.hasOwnProperty('id')) {
                taskCallsCount[data.id] = 1;
                waitForTask(data.id, product, data, callback, callback_data);
            } else {
                if (callback) {
                    callback(product, data, callback_data, true);
                }
            }
        },
        error: function (data) {
            if (callback) {
                callback(product, data, callback_data, false);
            }
        }
    });
}

function saveForLater(storeType, storeId, data, callback) {
    var postData = {
        store: storeId,
        data: JSON.stringify(data),
        original_data: JSON.stringify(data),
        b: true
    };

    var url = api_url('save-for-later', 'shopify');
    if (storeType === 'chq') {
        url = api_url('product-save', 'chq');
    } else if (storeType === 'gkart') {
        url = api_url('product-save', 'gkart');
    } else if (storeType === 'woo') {
        url = api_url('product-save', 'woo');
    }

    $.ajax({
        url: url,
        type: 'POST',
        data: JSON.stringify(postData),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        success: function (data) {
            $('[data-type="dropified"]').removeClass('hidden').attr('href', data.product.url);
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

function sendToStore(storeType, storeId, apiData, publish) {
    saveForLater(storeType, storeId, apiData, function(data, result) {
        var btn = $('#send-to-store');
        if (result === true) {
            var productId = data.product.id;
            if (storeType === 'shopify') {
                sendProductToShopify(apiData, storeId, productId, function (product, data) {
                    if (data.product) {
                        toastr.success("Product successfully exported", "Export");
                        $('[data-type="shopify"]').removeClass('hidden').attr('href', data.product.url);
                        updateButtonState(btn, 'reset');
                        toggleActions('show');
                    } else {
                        toastr.error("Product export failed", "Export");
                    }
                });
            } else if (storeType === 'chq') {
                sendProductToCommerceHQ(productId, storeId, publish, function(data) {
                    var pusher = new Pusher(data.pusher.key);
                    var channel_hash = data.pusher.channel;
                    var channel = pusher.subscribe(channel_hash);

                    channel.bind('product-export', function(data) {
                        if (data.product == productId) {
                            if (data.progress) {
                                btn.text(data.progress);
                                return;
                            }

                            updateButtonState(btn, 'reset');
                            toggleActions('show');
                            pusher.unsubscribe(channel_hash);

                            if (data.success) {
                                toastr.success('Product Exported.','CommerceHQ Export');
                                $('[data-type="chq"]').removeClass('hidden').attr('href', data.commercehq_url);
                            } else {
                                displayAjaxError('CommerceHQ Export', data);
                            }
                        }
                    });
                });
            } else if (storeType === 'woo') {
                sendProductToWooCommerce(productId, storeId, publish, function(data) {
                    var pusher = new Pusher(data.pusher.key);
                    var channel_hash = data.pusher.channel;
                    var channel = pusher.subscribe(channel_hash);

                    channel.bind('product-export', function(data) {
                        var productId = data.product;
                        if (data.product == productId) {
                            if (data.progress) {
                                btn.text(data.progress);
                                return;
                            }

                            updateButtonState(btn, 'reset');
                            toggleActions('show');
                            pusher.unsubscribe(channel_hash);

                            if (data.success) {
                                toastr.success('Product Exported.','WooCommerce Export');
                                $('[data-type="woo"]').removeClass('hidden').attr('href', data.woocommerce_url);
                            } else {
                                displayAjaxError('WooCommerce Export', data);
                            }
                        }
                    });
                });
            } else if (storeType === 'gkart') {
                sendProductToGrooveKart(productId, storeId, publish, function(data) {
                    var pusher = new Pusher(data.pusher.key);
                    var channel_hash = data.pusher.channel;
                    var channel = pusher.subscribe(channel_hash);

                    channel.bind('product-export', function(data) {
                        var productId = data.product;
                        if (data.product == productId) {
                            if (data.progress) {
                                btn.text(data.progress);
                                return;
                            }

                            updateButtonState(btn, 'reset');
                            toggleActions('show');
                            pusher.unsubscribe(channel_hash);

                            if (data.success) {
                                toastr.success('Product Exported.','GrooveKart Export');
                                $('[data-type="gkart"]').removeClass('hidden').attr('href', data.commercehq_url);
                            } else {
                                displayAjaxError('GrooveKart Export', data);
                            }
                        }
                    });
                });
            }
        }
    });
}

function toggleActions(state) {
    if (state == 'hide') {
        $('#store-actions .btn').addClass('hidden');
        $('#store-actions label').addClass('hidden');
    } else {
        $('#store-actions .btn').removeClass('hidden');
        $('#store-actions label').removeClass('hidden');
    }
}

function updateButtonState(button, state) {
    if($.fn.hasOwnProperty('bootstrapBtn')) {
        button.bootstrapBtn(state);
    } else {
        button.button(state);
    }
}

$(document).ready(function(){
    $('#save-for-later, #send-to-store').on('click', function(e) {
        e.preventDefault();
        if ($('.form-group.has-error').length) {
            displayAjaxError('Save Product', 'Your form still have errors');
            return;
        }
        var btn = $(this);
        var isSendToStore = btn.attr('id') == 'send-to-store';
        var storeType = $('#store-select option:selected').data('type');
        var storeId = $('#store-select').val();

        toggleActions('hide');
        btn.removeClass('hidden');
        $('.form-group.actions a').addClass('hidden');
        updateButtonState(btn, 'loading');

        $.ajax({
            url: $('#form-data').data('action'),
            type: 'POST',
            data: $('#form-data :input').serialize(),
            success: function (data) {
                $('[name="custom_product_id"]').val(data.custom_product_id);
                if (isSendToStore) {
                    sendToStore(storeType, storeId, data.api_data, true);
                } else {
                    saveForLater(storeType, storeId, data.api_data, function() {
                        updateButtonState(btn, 'reset');
                        toggleActions('show');
                        toastr.success("Product successfully saved", "Save");
                    });
                }
            },
            error: function (data) {
                toggleActions('show');
                updateButtonState(btn, 'reset');
                displayAjaxError('Saving Custom Product', data);
            }
        });
    });

    $('#only-save').on('click', function(e) {
        e.preventDefault();
        if ($('.form-group.has-error').length) {
            displayAjaxError('Save Product', 'Your form still have errors');
            return;
        }
        var btn = $(this);
        var storeType = $('#store-select option:selected').data('type');
        var storeId = $('#store-select').val();

        toggleActions('hide');
        btn.removeClass('hidden');
        updateButtonState(btn, 'loading');

        $.ajax({
            url: $('#form-data').data('action'),
            type: 'POST',
            data: $('#form-data :input').serialize(),
            success: function (data) {
                toggleActions('show');
                updateButtonState(btn, 'reset');
                $('[name="custom_product_id"]').val(data.custom_product_id);
            },
            error: function (data) {
                toggleActions('show');
                updateButtonState(btn, 'reset');
                displayAjaxError('Saving Custom Product', data);
            }
        });
    });
});
