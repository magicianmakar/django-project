function getVariantFromList(variantId, variants) {
    for (var i = 0, iLength = variants.length; i < iLength; i++) {
        var variant = variants[i];
        if (variant.id == variantId) {
            return variant;
        }
    }
    return null;
}

/*
 * Sizes
 */
function createSizeRow(size, customSize) {
    var tr = $('.size-variant[data-size-id="' + size.id + '"]');
    if (tr.length == 0) {
        tr = $('<tr class="size-variant">').attr('data-size-id', size.id);
    }
    var sizeTemplate = Handlebars.compile($("#size-variant").html());

    // Use specific size cost or default product cost
    var sku;
    var productCost = '0.00';
    var from = $('[name="ships_from"] option:selected');
    if (size[from.data('sku-key')]) {
        sku = size[from.data('sku-key')];
    } else {
        sku = from.val();
    }

    var cost = costBySku[sku];
    if (cost && cost.cost) {
        productCost = costBySku[sku].cost;
    }
    tr.html(sizeTemplate({'size': {
        'size': size.title,
        'title': customSize.title,
        'cost': productCost
    }}));
    $('#size-variants tbody').append(tr);

    if (customSize.deleted) {
        tr.addClass('deleted');
    }
}

function reloadCustomSizes() {
    $.each(layerAppCustomSizes, function(key, item) {
        var size = getVariantFromList(item.id, layerAppVariants.sizes);
        createSizeRow(size, item);
    });
}

if ($.isEmptyObject(layerAppCustomSizes)) {
    $.each(layerAppVariants.sizes, function(key, size) {
        layerAppCustomSizes[size.id] = {
            'id': size.id,
            'title': '',
            'size': size.title,
            'price': $('[name="price"]').val(),
            'sku': 'sizes:' + size.id,
            'china_sku': size.china_sku,
            'usa_sku': size.usa_sku
        };
        createSizeRow(size, layerAppCustomSizes[size.id]);
    });
} else {
    reloadCustomSizes();
}

$('.size-variant .delete, .size-variant .add').on('click', function() {
    var tr = $(this).parents('.size-variant');
    tr.toggleClass('deleted');
    if (tr.hasClass('deleted')) {
        layerAppCustomSizes[tr.data('size-id')].deleted = true;
    } else {
        layerAppCustomSizes[tr.data('size-id')].deleted = false;
    }
    generateVariants();
});

$('#size-variants tbody').on('change', '.input-size', function(e) {
    var sizeId = $(this).parents('.size-variant').data('size-id');
    var title = $(this).val();
    var wrapper = $(this).parents('.form-group');
    var isUnique = true;

    if (title) {
        var searchTitle = title.toLowerCase().trim();
        $.each(layerAppCustomSizes, function(k, item) {
            if (searchTitle == item.title.toLowerCase() || searchTitle == item.size.toLowerCase()) {
                isUnique = false;
                return false;
            }
        });
    }

    if (!isUnique) {
        wrapper.addClass('has-error');
    } else {
        wrapper.removeClass('has-error');
        layerAppCustomSizes[sizeId].title = title.trim();
        generateVariants();
    }
}).on('keyup', '.input-size:not(.changed)', function(e) {
    var sizeId = $(this).parents('.size-variant').data('size-id');
    if ($(this).val() && $(this).val() !== layerAppCustomSizes[sizeId].title) {
        $(this).addClass('changed');
    }
});


$('[name="ships_from"]').on('change', reloadCustomSizes);

function getNewUploader() {
    return new plupload.Uploader({
        runtimes: 'html5',
        browse_button: 'pickfiles',
        container: document.getElementById('plcontainer'),

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
                var name = randomPrefix + '_' + file.name;
                params.key = window.plupload_Config.paramsKey + name;
            }
        }
    });
}

/*
 * Styles
 */
function isStyleTitleUnique(title, variants, skipSku) {
    var isUnique = true;
    title = title.toLowerCase().trim();
    $.each(variants, function(k, item) {
        if (item.title.toLowerCase() == title && item.sku != skipSku) {
            isUnique = false;
            return false;
        }
    });
    return isUnique;
}

$.each(layerAppCustomStyles, function(key, item) {
    var variantIndex = item.sku.match(/variants(\d+):/)[1];

    var tr = $('<tr class="style-variant">').attr('variant-index', variantIndex);
    var styleTemplate = Handlebars.compile($("#style-variant").html());
    tr.html(styleTemplate({
        'variant': item
    }));
    $('#style-variants tbody').append(tr);

    if (item.deleted) {
        tr.addClass('deleted');
    }
});

function initCroppie(options) {
    /* Options:
     * - wrapper: div element used to load croppie
     * - width: exact width of mockup
     * - height: exact height of mockup
     * - fileInput: input from where the image will come from
    */
    var maxWidth = 250;
    var maxHeight = 150;
    var scaleWidth = maxWidth / options.width;
    var scaleHeight = maxHeight / options.height;
    var scale = Math.min(scaleWidth, scaleHeight);
    var cropWidth = options.width * scale;
    var cropHeight = options.height * scale;

    var initialized = false;
    var croppieElement = $(options.wrapper);

    options.fileInput.on('change', function() {
        if (!initialized) {
            initialized = true;
            croppieElement.croppie({
                enableExif: true,
                viewport: { width: cropWidth, height: cropHeight, type: 'square' },
                boundary: { width: maxWidth, height: maxHeight },
                showZoomer: true
            });
        }

        readFile(this, croppieElement);
    });
}

function readFile(input, croppieElement) {
    if (input.files && input.files[0]) {
        var reader = new FileReader();

        croppieElement.siblings('.awaiting-image').css('display', 'none');
        croppieElement.css('display', '');
        reader.onload = function(e) {
            croppieElement.croppie('bind', {
                url: e.target.result
            });
        };

        reader.readAsDataURL(input.files[0]);
    }
}

function toggleMockupDone(show) {
    if (show) {
        $('#variant-mockup .actions').hide();
        $('#variant-mockup .actions.done').show();
    } else {
        $('#variant-mockup .actions').show();
        $('#variant-mockup .actions.done').hide();
    }
}

var globalVariantIndex = 0;
var lastVariant = $('.style-variant:last');
if (lastVariant.length) {
    globalVariantIndex = parseInt(lastVariant.attr('variant-index'));
}
$('.add-variant').on('click', function() {
    var variantId = $(this).data('variant-id');
    var mockupTemplate = null;
    var isPaired = $(this).data('is-paired');
    var styleVariant = getVariantFromList(variantId, layerAppVariants.styles);

    if (styleVariant) {
        globalVariantIndex += 1;

        if (isPaired) {
            mockupTemplate = Handlebars.compile($("#variant-mockup-paired").html());
        } else {
            mockupTemplate = Handlebars.compile($("#variant-mockup-single").html());
        }

        $('#variant-mockup .modal-footer .mockup-save').bootstrapBtn('reset');
        $('#variant-mockup').attr('variant-index', globalVariantIndex);
        $('#variant-mockup .modal-footer .mockup-save').attr('is-paired', isPaired);
        $('#variant-mockup .modal-body').html(mockupTemplate({'style': styleVariant}));
        toggleMockupDone(false);
        $('#variant-mockup .modal-body .artwork').each(function() {
            var artworkElem = $(this);
            initCroppie({
                wrapper: artworkElem.find('.croppie'),
                width: styleVariant.artwork_width,
                height: styleVariant.artwork_height,
                fileInput: artworkElem.find('input[type="file"]')
            });
        });
        $('#variant-mockup').modal('show');
    }
});

$('#variant-mockup').on('hidden.bs.modal', function (e) {
    $('.croppie').croppie('destroy');
});

$('.mockup-save').on('click', function(e) {
    e.preventDefault();
    var btn = $(this);
    btn.bootstrapBtn('loading');

    var width = parseInt($('[name="mockup_artwork_width"]').val());
    var height = parseInt($('[name="mockup_artwork_height"]').val());
    var variantIndex = $('#variant-mockup').attr('variant-index');
    var variantId = $('[name="mockup_variant_id"]').val();
    var sku = 'variants' + variantIndex + ':' + variantId;

    formData = new FormData();
    formData.append('variant_id', variantId);
    formData.append('paired', $(this).attr('is-paired'));
    formData.append('sku', sku);

    var selectedStore = $('#store-select :selected');
    formData.append('store_type', selectedStore.data('type'));
    formData.append('store', selectedStore.val());

    var uploader = getNewUploader();

    // Images get lost when added before plupload is initialized
    uploader.bind('PostInit', function() {
        $.when.apply($, $('.croppie.croppie-container').map(function(key, item) {
            var croppieElement = $(item);
            var inputName = croppieElement.data('name');
            var inputKey = croppieElement.data('key');
            var d = $.Deferred();

            // Specific mockup size is required for mockup generation
            croppieElement.croppie('result', {
                type: 'blob',
                size: {width: width, height: height},
                format: 'jpeg',
                quality: 1
            }).then(function(image) {
                var filename = inputKey + '.jpg';
                uploader.addFile(image, filename);
                d.resolve({'file': filename, 'name': inputName, 'key': inputKey});
            });

            return d;
        })).then(function() {
            var inputData = {};
            $.each(arguments, function(k, input) {
                inputData[input.file] = input;
            });
            return inputData;
        }).done(function(inputData) {
            uploader.bind('FileUploaded', function(up, file, info) {
                var key = up.settings.multipart_params.key;
                var url = window.plupload_Config.uploadedUrl + key;
                formData.append(inputData[file.name].key, url);
            });

            uploader.bind('UploadProgress', function(up, file) {
                btn.text('Uploading ' + inputData[file.name].name + ' Image (' + file.percent + '%)');
            });

            uploader.bind('UploadComplete', function(up, files) {
                $.ajax({
                    url: api_url('mockup', 'prints'),
                    type: 'POST',
                    data: formData,
                    contentType: false,
                    processData: false,
                    context: {'variantIndex': variantIndex, 'sku': sku, 'btn': btn},
                    success: function(data) {
                        btn.html("<i class='fa fa-circle-o-notch fa-spin'></i> Generating...");
                        var pusher = new Pusher(data.pusher.key);
                        var channel_hash = data.pusher.channel;
                        var channel = pusher.subscribe(channel_hash);

                        channel.bind('prints-mockup', function(data) {
                            if (data.sku == sku) {
                                if (data.success) {
                                    var styleVariant = getVariantFromList(data.variant_id, layerAppVariants.styles);

                                    var tr;
                                    if (!layerAppCustomStyles[variantIndex]) {
                                        tr = $('<tr class="style-variant">').attr({
                                            'variant-index': variantIndex,
                                            'variant-sku': data.sku
                                        });
                                        $('#style-variants tbody').append(tr);
                                    } else {
                                        tr = $('#style-variants .style-variant[variant-index="' + variantIndex + '"]');
                                    }

                                    layerAppCustomStyles[variantIndex] = {
                                        'id': data.variant_id,
                                        'title': styleVariant.variant_name + ' ' + variantIndex,
                                        'style': styleVariant.variant_name,  // Original title
                                        'image': data.mockup,
                                        'image_hash': data.mockup_hash,
                                        'sku': sku,
                                        'artworks': data.artworks,
                                    };

                                    if (data.artworks.length == 2 && data.artworks[0] === data.artworks[1]) {
                                        addImages([data.mockup, data.artworks[0]]);
                                    } else {
                                        addImages([data.mockup].concat(data.artworks));
                                    }

                                    var styleTemplate = Handlebars.compile($("#style-variant").html());
                                    tr.html(styleTemplate({
                                        'variant': layerAppCustomStyles[variantIndex]
                                    }));
                                    if (!isStyleTitleUnique(styleVariant.variant_name, layerAppCustomStyles, sku)) {
                                        $(this).parents('.form-group').addClass('has-error');
                                    }

                                    if ($('#variant-mockup').attr('variant-index') == variantIndex) {
                                        $('#variant-mockup .modal-body img.img-responsive').attr('src', data.mockup);
                                    }

                                    generateVariants();
                                    btn.bootstrapBtn('reset');
                                    toggleMockupDone(true);
                                } else if (data.error) {
                                    generateVariants();
                                    btn.bootstrapBtn('reset');
                                    toggleMockupDone(true);
                                    displayAjaxError('Generate Variant Image', data);
                                }
                            }
                        });
                    },
                    error: function(data) {
                        generateVariants();
                        btn.bootstrapBtn('reset');
                        toggleMockupDone(true);
                        displayAjaxError('Generate Variant Image', data);
                    }
                });
            });
            uploader.start();
        });
    });
    uploader.init();
});

$('#style-variants tbody').on('click', '.style-variant .delete, .style-variant .add', function() {
    var tr = $(this).parents('.style-variant');
    var variantIndex = tr.attr('variant-index');
    tr.toggleClass('deleted');
    if (tr.hasClass('deleted')) {
        layerAppCustomStyles[variantIndex].deleted = true;
    } else {
        layerAppCustomStyles[variantIndex].deleted = false;
    }
    generateVariants();
});

$('#style-variants tbody').on('click', '.style-variant .erase', function() {
    var tr = $(this).parents('.style-variant');
    var variantIndex = tr.attr('variant-index');
    var variantSku = tr.attr('variant-sku');
    delete layerAppCustomStyles[variantIndex];

    $('tr[variant-sku*="' + variantSku + '"]').remove();
    tr.remove();
    generateVariants();
});

$('#style-variants tbody').on('change', '.input-style', function() {
    var variantIndex = $(this).parents('.style-variant').attr('variant-index');
    var title = $(this).val();
    var wrapper = $(this).parents('.form-group');

    if (!title || !isStyleTitleUnique(title, layerAppCustomStyles)) {
        wrapper.addClass('has-error');
    } else {
        wrapper.removeClass('has-error');
        layerAppCustomStyles[variantIndex].title = title.trim();
        generateVariants();
    }
}).on('keyup', '.input-style:not(.changed)', function(e) {
    var variantIndex = $(this).parents('.style-variant').attr('variant-index');
    if ($(this).val() !== layerAppCustomStyles[variantIndex].title) {
        $(this).addClass('changed');
    }
});

/*
 * Merge Sizes and Styles
 */
function cartesianProduct(arr) {
    return arr.reduce(function (a, b) {
        return a.map(function (x) {
            return b.map(function (y) {
                return x.concat(y);
            });
        }).reduce(function (a, b) {
            return a.concat(b);
        }, []);
    }, [[]]);
}

function generateVariants() {
    if ($('.form-group.has-error').length) {
        return;
    }

    var styles = $.map(layerAppCustomStyles, function(value, key) { return value; });
    var sizes = $.map(layerAppCustomSizes, function(value, key) { return value; });
    var cartesian = cartesianProduct([styles, sizes]);

    var price = parseFloat($('[name="price"]').val());
    var compareAt = parseFloat($('[name="compare_at_price"]').val());
    var ships_from = $('[name="ships_from"] option:selected').data('sku-key');

    for (var i = 0, iLength = cartesian.length; i < iLength; i++) {
        var items = cartesian[i];
        var isDeletedSku = items.reduce(function(a, b) {
            if (a.deleted || b.deleted) return [a.sku, b.sku].join(';');
        });
        if (isDeletedSku) {
            delete customVariantsInfo[isDeletedSku];
            $('#variants tbody tr[variant-sku="' + isDeletedSku + '"]').remove();
            continue;
        }

        var variant = {title: [], image: '', sku: [], price: price, compare_at: compareAt};
        for (var j = 0, jLength = items.length; j < jLength; j++) {
            var item = items[j];
            // Original title is different for each type of variant
            var customTitle = item.title || item.style || item.size;
            variant.title.push(customTitle);
            variant.sku.push(item.sku);
            if (item.image) {
                variant.image = item.image;
            }

            // Set new price and compare from SKU of selected shipping country
            if (item[ships_from]) {
                var updatedCost = costBySku[item[ships_from]];
                if (updatedCost) {
                    variant.price = updatedCost.price;
                    variant.compare_at = updatedCost.compare_at;
                }
            }
        }
        variant.title = variant.title.join(' / ');
        variant.sku = variant.sku.join(';');

        if (!customVariantsInfo[variant.sku]) {
            customVariantsInfo[variant.sku] = variant;
        } else {
            customVariantsInfo[variant.sku].title = variant.title;
            customVariantsInfo[variant.sku].image = variant.image;
        }

        var tr = $('#variants tbody tr[variant-sku="' + variant.sku + '"]');
        if (tr.length == 0) {
            tr = $('<tr class="variant">').attr('variant-sku', variant.sku);
            $('#variants tbody').append(tr);
        }

        var variantTemplate = Handlebars.compile($("#variant").html());
        tr.html(variantTemplate({'variant': customVariantsInfo[variant.sku]}));
    }

    // Necessary data for variants mapping and placing orders
    $('[name="variants"]').val(JSON.stringify(customVariantsInfo));
    $('[name="extra_data"]').val(JSON.stringify({
        'styles': {
            'title': $('[name="style_type"]').val() || 'Style',
            'data': layerAppCustomStyles
        },
        'sizes': {
            'title': $('[name="size_type"]').val() || 'Size',
            'data': layerAppCustomSizes
        },
        'variants_mapping': [{
            'title': $('[name="style_type"]').val(),
            'values': $.map(layerAppCustomStyles, function(e) {
                if (e.deleted) return null;
                return {'title': e.title, 'image': e.image, 'sku': e.sku};
            })
        }, {
            'title': $('[name="size_type"]').val(),
            'values': $.map(layerAppCustomSizes, function(e) {
                if (e.deleted) return null;
                return {'title': e.title || e.size, 'image': false, 'sku': e.sku};
            })
        }]
    }));
}

if (!$.isEmptyObject(customVariantsInfo)) {
    var customVariantsBySku = {};
    $.each(customVariantsInfo, function(k, i) {
        customVariantsBySku[i.sku] = i;
    });
    customVariantsInfo = customVariantsBySku;
    generateVariants();
}

$('#variants tbody').on('change', '.price, .compare_at', function() {
    var input = $(this);
    var variantSku = input.parents('.variant').attr('variant-sku');
    var inputName = 'price';
    if (input.hasClass('compare_at')) {
        inputName = 'compare_at';
    }

    var newValue = parseFloat(input.val());
    if (!newValue || isNaN(newValue)) {
        newValue = 0.0;
    }
    customVariantsInfo[variantSku][inputName] = newValue;
    $('[name="variants"]').val(JSON.stringify(customVariantsInfo));
});

$('#style-variants, #size-variants').on('click', '.confirm-input', function(e) {
    e.preventDefault();
    $(this).siblings('.changed').removeClass('changed');
});
