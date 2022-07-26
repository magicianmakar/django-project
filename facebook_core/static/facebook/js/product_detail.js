/* global $, config, toastr, swal, product, product:true, renderImages, allPossibleCases */
/* global setup_full_editor, cleanImageLink, displayAjaxError, api_url, variants, variantsConfig, productDetails, JSZip, JSZipUtils, Pusher */

(function(config, product, variants, variantsConfig, productDetails) {
'use strict';

var image_cache = {};

function showProductInfo(rproduct) {
    product = rproduct;
    if (product) {
        $('#product-title').val(product.title);
        $('#product-type').val(product.product_type);
        $('#product-tag').val(product.tags);
        $('#product-vendor').val(product.vendor);

        if (variantsConfig.length && !config.connected) {
            variantsConfig.forEach(function(el) {
                var v = $('#variants .variant-simple').clone();
                v.removeClass('variant-simple');
                v.addClass('variant');
                v.find("a.remove-variant").click(removeVariant);
                v.show();

                v.find('#product-variant-name').val(el.title);
                v.find('#product-variant-values').val(el.values.join(','));

                $("#product-variant-values", v).tagit({
                    allowSpaces: true
                });

                $('#variants .area').append(v);
            });
        }

        if (product.product_description) {
            $('#product-description').val(product.product_description);
        }

        renderImages();
    }
}

function prepareApiData(productData, variants) {
    // Get all default SureDone fields + fb category specific fields

    var apiData = {
        title: $('#product-title').val().trim(),
        guid: productData.guid,
        producttype: $('#product-type').val().trim(),
        tags: $('#product-tag').val(),
        longdescription: $('#product-description').val().trim(),
        fb_category_id: productData.fb_category_id,
        fb_category_name: productData.fb_category_name,
        status: productData.status,
        vendor: $('#product-vendor').val(),
        published: $('#product-visible').prop('checked'),
        images: productData.images,
        variants: [],
        brand: productData.brand,
        page_link: productData.page_link,
    };

    if ('extendedFieldsList' in productData) {
        productData.extendedFieldsList.forEach(function(key) {
            if (key in productData && productData[key] !== undefined && productData[key].trim() !== '') {
                apiData[key] = productData[key].trim();
            }
        });
    }

    var attrs = ['price', 'compareatprice', 'weight', 'weightunit', 'stock', 'suppliersku'];

    if (variants.length > 0) {
        // TODO: when modifying variants is implemented, add this back
        /*if (config.connected || $('#advanced_variants').prop('checked')) {*/
        $('#fb-variants tr.fb-variant').each(function(j, tr) {
            var variant_data = variants[j];

            $.each(attrs, function(k, att) {
                var att_val = $('[name="' + att + '"]', tr).val();
                if (att_val !== undefined) {
                    variant_data[att] = att_val;
                }
            });

            apiData.variants.push(variant_data);

        });
        /*} else {
            var updatedVariantsConfig = [];
            $('#variants .variant').each(function (i, el) {
                updatedVariantsConfig.push({
                    'title': $(el).find('#product-variant-name').val(),
                    'values': $(el).find('#product-variant-values').val().split(',')
                });
            });
            variantsConfig = updatedVariantsConfig;
            apiData.variants = variants.filter(function(variant) {
                return updatedVariantsConfig.every(function (varConfig) {
                    var keyExists = varConfig.title in variant;
                    var valueExists = varConfig.values.includes(variant[varConfig.title]);
                    return keyExists && valueExists;
                });
            }).map(function(variant) {
                variant.variantsconfig = JSON.stringify(updatedVariantsConfig);
                return variant;
            });
        }*/
    }

    return apiData;
}

function verifyPusherIsDefined() {
    if (typeof(Pusher) === 'undefined') {
        toastr.error('This could be due to using Adblocker extensions<br>' +
            'Please whitelist Dropified website and reload the page<br>' +
            'Contact us for further assistance',
            'Pusher service is not loaded', {timeOut: 0});
        return false;
    }
    return true;
}

$("#txtSearch").autocomplete({
    source: "/ajax_calls/search/",
    minLength: 2,
    open: function(){
        setTimeout(function () {
            $('.ui-autocomplete').css('z-index', 99);
        }, 0);
    }
  });

var elems = Array.prototype.slice.call(document.querySelectorAll('.js-switch'));
elems.forEach(function(html) {
    var switchery = new Switchery(html, {
        color: '#93c47d',
        size: 'small'
    });
});

$('.tab-nav-notes').click(function() {
    window.location.hash = '#notes';
});

$('.connections-tab').click(function() {
    window.location.hash = '#connections';
});

$('.tab-nav-reviews').click(function() {
    window.location.hash = '#reviews';
});

$('.tab-nav-alerts').click(function() {
    window.location.hash = '#alerts';
});

$('.tab-nav-edit').click(function() {
    window.location.hash = '#edit';
});

$("#alert_price_change").change(function() {
    var alert_price_change = $(this).val();
    $(".price-update-option").hide();
    $(".price-update-option[data-value='" + alert_price_change + "']").show();
});
$("#alert_price_change").change();

$("a.add-variant").click(function (e) {
    e.preventDefault();

    var v = $('#variants .variant-simple').clone();
    v.addClass('variant');
    v.removeClass('variant-simple');
    v.show();
    v.find("a.remove-variant").click(removeVariant);

    $("#product-variant-values", v).tagit({
        allowSpaces: true
    });

    $('#variants .area').append(v);
});

function removeVariant(e) {
    e.preventDefault();

    $(e.target).parent().remove();
}

function verifyRequiredFields() {
    var allRequiredFields = $('#product-edit-form :input').filter('[required]:visible');
    var invalidFields = 0;
    allRequiredFields.each( function () {
        if (this.value.trim() === '') {
            invalidFields++;
            $(this).parent().addClass('has-error');
        } else {
            $(this).parent().removeClass('has-error');
        }
    });

    if (invalidFields > 0) {
        swal('Product Export', 'Please fill out all required fields first!', 'error');
        return false;
    }

    return true;
}

$('#product-export-btn').click(function (e) {
    e.preventDefault();

    if (!verifyRequiredFields()) {
        return;
    }

    if (!validatePriceValue()) {
        return;
    }

    var btn = $(this);

    productSave($('#product-save-btn'), function () {
        productExport(btn);
    });
});

function validatePriceValue() {
    var priceError = 0;
    var comparePriceError = 0;
    var productPrice, productPriceVal, compareAtPrice, compareAtPriceVal;

    $('#fb-variants').find('.fb-variant').each(function() {
        productPrice = $(this).find('input[name="price"]');
        compareAtPrice = $(this).find('input[name="compareatprice"]');
        productPriceVal = parseFloat(productPrice.val());
        compareAtPriceVal = parseFloat(compareAtPrice.val());

        if (isNaN(productPriceVal) || productPriceVal < 0.99) {
            productPrice.parent().addClass('has-error');
            priceError++;
        } else {
            productPrice.parent().removeClass('has-error');
        }

        if (!isNaN(compareAtPriceVal) && compareAtPriceVal !== 0 && productPriceVal > compareAtPriceVal) {
            comparePriceError++;
            compareAtPrice.parent().addClass('has-error');
        } else {
            compareAtPrice.parent().removeClass('has-error');
        }
    });

    if (priceError) {
        swal('Invalid Price Value', 'Prices must be greater than or equal to 0.99.', 'error');
        return false;
    }

    if (comparePriceError) {
        swal('Invalid Compare Price Value', 'Compare price value must be greater than or equal to the current price.', 'error');
        return false;
    }

    return true;
}

function productExport(btn) {
    var store_id = $('#store-select').val();
    if (!store_id || store_id.length === 0) {
        swal('Product Export', 'Please choose an Facebook store first!', 'error');
        return;
    }
    if (!verifyPusherIsDefined()) {
        return;
    }

    btn.bootstrapBtn('loading');

    var pusher = new Pusher(config.sub_conf.key);
    var channel = pusher.subscribe(config.sub_conf.channelUser);

    channel.bind('fb-product-export', function(eventData) {
        if (eventData.product === product.guid) {
            if (eventData.progress) {
                btn.text(eventData.progress);
                return;
            }

            btn.bootstrapBtn('reset');
            pusher.unsubscribe(channel);

            if (eventData.success) {
                swal('Facebook Product Export', 'Please wait a few minutes for a product to get published on Facebook.' +
                    ' It may take up to an hour for a product to appear to Facebook.', 'success');

                var alerts = $('#alerts-col');
                alerts.empty();
                alerts.append('<div class="alert alert-info" role="alert">' +
                    '<i class="fa fa-info-circle"></i>&nbsp;' +
                    'A product export has been queued and is pending.' +
                    '</div>');

                // setTimeout(productErrorLog, 3 * 60000);
            } else {
                displayAjaxError('Facebook Export', eventData, true);
            }
        }
    });

    channel.bind('pusher:subscription_succeeded', function() {
        $.ajax({
            url: api_url('product-export', 'fb'),
            type: 'POST',
            data: {
                'product': product.guid,
                'store': store_id,
            },
            context: {btn: btn},
            success: function (data) {},
            error: function (data) {
                btn.bootstrapBtn('reset');
                pusher.unsubscribe(channel);
                displayAjaxError('Facebook Export', data, true);
            }
        });
    });
}

function productErrorLog() {
    var store_id = $('#store-select').val();
    if (!verifyPusherIsDefined()) {
        return;
    }

    var pusher = new Pusher(config.sub_conf.key);
    var channel = pusher.subscribe(config.sub_conf.channelUser);

    channel.bind('fb-product-latest-relist-log', function(eventData) {
        if (eventData.product === product.guid) {
            if (eventData.progress) {
                return;
            }
            pusher.unsubscribe(channel);

            if (!eventData.error && !eventData.warning) {
                return;
            }

            var alerts = $('#alerts-col');
            alerts.empty();
            var log;
            try {
                log = JSON.parse(eventData.log);
            } catch (e) {}

            if (eventData.error) {
                alerts.append(
                    '<div class="alert alert-danger" role="alert">' +
                    '<i class="fa fa-times-circle-o"/>&nbsp;' + log.message +
                    '</div>');
                if (log.errors) {
                    $('#alerts-col .alert').append('<ul></ul>');
                    log.errors.forEach(function(item) {
                         $('#alerts-col .alert ul').append('<li>' + item + '</li>');
                    });
                }
            } else if (eventData.warning) {
                alerts.empty();
                alerts.append(
                    '<div class="alert alert-warning" role="alert">' +
                    '<i class="fa fa-exclamation-triangle"/>&nbsp;' + log.message +
                    '</div>');
                if (log.warnings) {
                    $('#alerts-col .alert').append('<ul></ul>');
                    log.warnings.forEach(function(item) {
                         $('#alerts-col .alert ul').append('<li>' + item + '</li>');
                    });
                }
            }
        }
    });

    channel.bind('pusher:subscription_succeeded', function() {
        $.ajax({
            url: api_url('product-latest-relist-log', 'fb'),
            type: 'GET',
            data: {
                'product': product.guid,
                'store': store_id,
            },
            success: function (data) {},
            error: function (data) {}
        });
    });
}

$('#product-update-btn').click(function (e) {
    e.preventDefault();
    var store_id = $('#store-select').val();

    if (!verifyPusherIsDefined()) {
        return;
    }

    var btn = $(this);
    btn.bootstrapBtn('loading');

    var apiData = prepareApiData(product, variants, variantsConfig);

    var pusher = new Pusher(config.sub_conf.key);
    var channel = pusher.subscribe(config.sub_conf.channelUser);

    channel.bind('fb-product-update', function(eventData) {
        if (eventData.product === product.guid) {
            if (eventData.progress) {
                btn.text(eventData.progress);
                return;
            }

            btn.bootstrapBtn('reset');
            pusher.unsubscribe(channel);

            if (eventData.success) {
                toastr.success('Product Updated.','Facebook Update');
                setTimeout(function() {
                    window.location.href = 'product_url' in eventData ? eventData.product_url : '/fb/products';
                }, 1000);
            }
            if (eventData.error) {
                displayAjaxError('Facebook Update', eventData, true);
            }
        }
    });

    channel.bind('pusher:subscription_succeeded', function() {
        $.ajax({
            url: api_url('product-update', 'fb'),
            type: 'POST',
            data: JSON.stringify ({
                product_data: JSON.stringify(apiData),
                site_id: product.fb_site_id,
                store: store_id,
            }),
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            context: {btn: btn},
            success: function (data) {},
            error: function (data) {
                btn.bootstrapBtn('reset');
                pusher.unsubscribe(channel);
                displayAjaxError('Update Product', data);
            }
        });
    });
});

function showAdvancedVariantsView() {
    $('#variants').hide();
    $('#fb-variants').show();
    $('#fb-variants-panel-container').show();
}

function showSimpleVariantsView() {
    $('#variants').show();
    $('#fb-variants-panel-container').hide();
    $('#fb-variants').hide();
}

$('#advanced_variants').on('change', function(){
    if($(this).prop('checked')) {
        showAdvancedVariantsView();
    } else {
        showSimpleVariantsView();
    }
});

function deleteProduct(productGuid) {
    if (!verifyPusherIsDefined()) {
        return;
    }

    var pusher = new Pusher(config.sub_conf.key);
    var channel = pusher.subscribe(config.sub_conf.channel);

    channel.bind('product-delete', function(eventData) {
        if (eventData.product === product.guid) {
            swal.close();
            pusher.unsubscribe(channel);

            if (eventData.success) {
                toastr.success("The product has been deleted.", "Deleted!");
                setTimeout(function() {
                    window.location.href = 'redirect_url' in eventData ? eventData.redirect_url : '/fb/products';
                }, 1000);
            }
            if (eventData.error) {
                displayAjaxError('Delete Product', eventData);
            }
        }
    });

    channel.bind('pusher:subscription_succeeded', function() {
        $.ajax({
            url: api_url('product', 'fb') + '?' + $.param({product: productGuid}),
            type: 'DELETE',
            success: function(data) {},
            error: function(data) {
                pusher.unsubscribe(channel);
                displayAjaxError('Delete Product', data);
            }
        });
    });
}

$('.delete-product-btn').click(function(e) {
    e.preventDefault();

    var btn = $(this);
    var guid = btn.attr('product-id');

    swal({
            title: "Delete Product",
            text: "This will remove the product permanently. Are you sure you want to remove this product?",
            type: "warning",
            showCancelButton: true,
            closeOnConfirm: false,
            showLoaderOnConfirm: true,
            confirmButtonColor: "#DD6B55",
            confirmButtonText: "Remove Permanently",
            cancelButtonText: "Cancel"
        },
        function(isConfirmed) {
            if (isConfirmed) {
                deleteProduct(guid);
            }
        });
});

$('#modal-pick-variant').on('show.bs.modal', function(e) {
    $('#pick-variant-btn').html('Select Variant Type<span class="caret" style="margin-left:10px"></span>');
    $('#pick-variant-btn').val('');
    $('#split-variants-count').text('0');
    $('#split-variants-values').text('');
});

$('#modal-pick-variant .dropdown-menu li a').click(function(e) {
    var val = $(this).text();
    $('#pick-variant-btn').html($(this).text() + '<span class="caret" style="margin-left:10px"></span>');
    $('#pick-variant-btn').val(val);
    var targetVariants = variantsConfig.find(function(variant) {
        return variant.title === val;
    }).values;

    $('#split-variants-count').text(targetVariants.length);
    $('#split-variants-values').text(targetVariants.join(', '));
});

$('#btn-split-variants').click(function (e) {
    e.preventDefault();
    $('#modal-pick-variant').modal('show');
});

$('#modal-pick-variant .btn-submit').click(function(e) {
    var split_factor = $('#pick-variant-btn').val();
    if (!split_factor) {
        swal('Please specify a variant type for split.');
        return;
    }
    if ($('#split-variants-count') === '0') {
        swal('There should be more than one variant to split it.');
        return;
    }

    var product_id = config.product_id;

    $(this).bootstrapBtn('loading');

    $.ajax({
        url: api_url('product-split-variants', 'fb'),
        type: 'POST',
        data: {
            product: product_id,
            split_factor: split_factor,
        },
        context: {btn: $(this)},
        success: function (data) {
            var btn = this.btn;
            btn.bootstrapBtn('reset');

            if ('products_ids' in data) {
                // check if current product is already connected to shopify..
                if ($('#product-export-btn').attr('target') === 'shopify-update') {
                  toastr.success('The variants are now split into new products.\r\n' +
                    'The new products will get connected to shopify very soon.', 'Product Split!');
                } else {
                  toastr.success('The variants are now split into new products.', 'Product Split!');
                }
                setTimeout(function() { window.location.href = '/fb/products'; }, 500);
            }
        },
        error: function (data) {
            this.btn.bootstrapBtn('reset');

            displayAjaxError('Split variants into separate products', data);
        }
    });

    $('#modal-pick-variant').modal('hide');
});

$('#product-save-btn').click(function (e) {
    if (config.connected && !verifyRequiredFields()) {
        return;
    }

    var btn = $(this);
    productSave(btn, function () {
        toastr.success('Product changes saved!','Product Saved');
    });

});

function productSave(btn, callback) {
    if (!verifyPusherIsDefined()) {
        return;
    }

    btn.bootstrapBtn('loading');
    var store_id = $('#store-select').val();

    var apiData = prepareApiData(product, variants, variantsConfig);

    var pusher = new Pusher(config.sub_conf.key);
    var channel = pusher.subscribe(config.sub_conf.channelUser);

    channel.bind('fb-product-update', function(eventData) {

        if (eventData.product === product.guid) {
            if (eventData.progress) {
                btn.text(eventData.progress);
                return;
            }

            btn.bootstrapBtn('reset');
            pusher.unsubscribe(channel);

            if (eventData.success && callback) {
                callback();
            }
            if (eventData.error) {
                displayAjaxError('Save Product', eventData, true);
            }
        }
    });

    channel.bind('pusher:subscription_succeeded', function() {

        $.ajax({
            url: api_url('product-update', 'fb'),
            type: 'POST',
            data: JSON.stringify ({
                store: store_id,
                product_data: JSON.stringify(apiData),
                site_id: product.fb_site_id,
                skip_publishing: true,
                variants_config: JSON.stringify(variantsConfig)
            }),
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            context: {btn: btn},
            success: function (data) {},
            error: function (data) {
                pusher.unsubscribe(channel);
                btn.bootstrapBtn('reset');
                displayAjaxError('Save Product', data, true);
            },
        });
    });
}

$("#view-btn").click(function () {
    window.open($(this).attr('shopify-url'), '_blank');
});

$('#duplicate-btn').click(function (e) {
    if ($(this).attr('href') != '#') {
        return;
    }

    e.preventDefault();

    if (!verifyPusherIsDefined()) {
        return;
    }

    var btn = $('#duplicate-btn');
    var pusher = new Pusher(config.sub_conf.key);
    var channel = pusher.subscribe(config.sub_conf.channel);

    btn.bootstrapBtn('loading');
    btn.addClass('disabled');

    channel.bind('product-duplicate', function (eventData) {
        if (eventData.product === product.guid) {
            pusher.unsubscribe(channel);
            if (eventData.success) {
                toastr.success('Duplicate Product.','Product Duplicated!');
                setTimeout(function() { window.open(eventData.duplicated_product_url, '_blank'); }, 1000);
            }
            if (eventData.error) {
                displayAjaxError('Duplicate Product', eventData);
            }
            btn.bootstrapBtn('reset');
            btn.removeClass('disabled');
        }
    });

    channel.bind('pusher:subscription_succeeded', function () {
        $.ajax({
            url: api_url('product-duplicate', 'fb'),
            type: 'POST',
            data: {
                product: product.sku
            },
            success: function (data) { },
            error: function (data) {
                pusher.unsubscribe(channel);
                displayAjaxError('Duplicate Product', data);
                btn.bootstrapBtn('reset');
                btn.removeClass('disabled');
            }
        });
    });
});

function matchImagesWithExtra() {
    $('#modal-add-image .extra-added').remove();
    $('#modal-add-image .add-var-image-block').each(function(i, el) {
            if (indexOfImages(product.images, $('img', el).attr('src')) != -1) {
                $(el).append($('<img class="extra-added" src="//i.imgur.com/HDg5nrv.png" ' +
                    'style="position:absolute;left:16px;top:1px;border-radius:0 0 8px 0;' +
                    'background-color:#fff;">'));
            }
    });
}

function imageClicked(e) {
    var imageID = $(e.target).parents('.var-image-block').find('img').attr('image-id');
    var new_images = [];

    for (var i = 0; i < product.allImages.length; i++) {
        if (i != imageID) {
            new_images.push(product.allImages[i]);
        }
    }

    product.allImages = product.images = product.media_links = new_images;
    $(e.target).parent().remove();

    renderImages();
}

$('.var-image-block button').click(imageClicked);

$('.var-image-block').mouseenter(function() {
    $(this).find('button').show();
})
.mouseleave(function() {
    $(this).find('button').fadeOut();
});

$('#save-product-notes').click(function (e) {
    var btn = $(this);

    btn.bootstrapBtn('loading');

    $.ajax({
        type: 'POST',
        url: api_url('product-notes', 'fb'),
        context: btn,
        data: {
            'notes': $('#product-notes').val(),
            'product': config.product_guid,
        },
        success: function(data) {
            if (data.status == 'ok') {
                toastr.success('Modification saved.','Product Notes');
            } else {
                displayAjaxError('Product Notes', data);
            }
        },
        error: function(data) {
            displayAjaxError('Product Notes', data);
        },
        complete: function() {
            btn.bootstrapBtn('reset');
        }
    });
});

$('.export-add-btn').click(function (e) {
    e.preventDefault();

    var default_export = config.exports.length ? {
        product: config.product_guid
    } : config.default_export;

    if (config.exports.length) {
        default_export.shopify = config.exports[0].shopify;
    }

    var el = $(export_template(default_export));

    $('#export-container').append(el);

    bindExportEvents(el);
});

function bindExportEvents(target) {
    target = typeof(target) === 'undefined' ? document : target;

    $('.sync-inventory-btn', target).click(function(e) {
        e.preventDefault();

        var btn = $(this);
        var form = $(this).parents('.product-export-form');

        btn.bootstrapBtn('loading');

        $.ajax({
            type: 'POST',
            url: api_url('sync_with_supplier', 'fb'),
            context: btn,
            data: {
                'product': form.data('product-id'),
            },
            success: function(data) {
                toastr.success('It may take a couple of minutes to complete.', 'Inventory Syncing Started');
            },
            error: function(data) {
                displayAjaxError('Inventory Syncing', data);
            },
            complete: function() {
                btn.bootstrapBtn('reset');
            }
        });
    });


    $('.export-save-btn', target).click(function (e) {
        e.preventDefault();

        var btn = $(this);
        var form = $(this).parents('.product-export-form');

        btn.bootstrapBtn('loading');

        $.ajax({
            type: 'POST',
            url: api_url('supplier', 'fb'),
            context: btn,
            data: {
                'original-link': $('.product-original-link', form).val(),
                'shopify-link': $('.product-shopify-link', form).val(),
                'supplier-name': $('.product-supplier-name', form).val(),
                'supplier-link': $('.product-supplier-link', form).val(),
                'product': product.guid,
                'export': form.data('export-id'),
            },
            success: function(data) {
                toastr.success('Modification saved.','Product Connections');

                if (data.reload) {
                    setTimeout(function() {
                        window.location.hash = 'connections';
                        window.location.reload();
                    }, 200);
                }
            },
            error: function(data) {
                displayAjaxError('Product Connections', data);
            },
            complete: function() {
                btn.bootstrapBtn('reset');
            }
        });
    });

    $('.export-default-btn', target).click(function (e) {
        e.preventDefault();

        var btn = $(this);
        var form = $(this).parents('.product-export-form');

        btn.bootstrapBtn('loading');

        $.ajax({
            type: 'POST',
            url: api_url('supplier-default', 'fb'),
            context: btn,
            data: {
                'product': product.guid,
                'export': form.data('export-id'),
            },
            success: function(data) {
                toastr.success('Default Supplier Changed.','Product Connections');

                setTimeout(function() {
                    window.location.hash = '#connections';
                    window.location.reload();
                }, 200);
            },
            error: function(data) {
                displayAjaxError('Product Connections', data);
            },
            complete: function() {
                btn.bootstrapBtn('reset');
            }
        });
    });

    $('.export-delete-btn', target).click(function (e) {
        e.preventDefault();

        var btn = $(this);
        var form = $(this).parents('.product-export-form');

        if (!form.data('export-id')) {
            $(this).parents('.export').remove();
            return;
        }
        swal({
            title: 'Delete Supplier',
            text: 'Are you sure you want to delete this Supplier?',
            type: "warning",
            showCancelButton: true,
            animation: false,
            cancelButtonText: "Cancel",
            confirmButtonText: 'Yes',
            confirmButtonColor: "#DD6B55",
            closeOnCancel: true,
            closeOnConfirm: false,
            showLoaderOnConfirm: true,
        },
        function(isConfirm) {
            if (isConfirm) {
                btn.bootstrapBtn('loading');

                $.ajax({
                    type: 'DELETE',
                    url: api_url('supplier', 'fb') + '?' + $.param({
                        'product': product.guid,
                        'supplier': form.data('export-id'),
                    }),
                    context: btn,
                    success: function(data) {
                        toastr.success('Supplier Deleted.','Product Connections');
                        swal.close();

                        setTimeout(function() {
                            window.location.hash = '#connections';
                            window.location.reload();
                        }, 200);
                    },
                    error: function(data) {
                        displayAjaxError('Product Connections', data);
                    },
                    complete: function() {
                        btn.bootstrapBtn('reset');
                    }
                });
            }
        });
    });

    $('.product-original-link', target).bindWithDelay('keyup', function (e) {

        var input = $(e.target);
        var parent = input.parents('.export');
        var product_url = input.val().trim();

        renderSupplierInfo(product_url, parent);
    }, 200);
}

$('#modal-add-image').on('show.bs.modal', function (e) {
    $('#modal-add-image .description-images-add').empty();
    var counter=0;
    $('.original-description img').each(function (i, el) {
        if (indexOfImages(config.product_extra_images, $(el).attr('src'))==-1) {
            if (counter % 4 === 0) {
                $('.description-images-add').append($('<div class="col-xs-12"></div>'));
            }

            var d = $('<div>', {
                'class': 'col-xs-3 add-var-image-block',
                'image-url': $(el).attr('src')
            });
            var img = $('<img>', {
                src: $(el).attr('src'),
                'class': 'add-var-image',
                'image-url': $(el).attr('src'),
                'style': ''
            });

            d.append(img);

            img.click(function (e) {
                var imageIdx = indexOfImages(product.images, $(this).attr('src'));
                if (imageIdx == -1) {
                    product.images.push($(this).attr('src'));
                } else {
                    var images = [];

                    for (var i = 0; i < product.images.length; i++) {
                        if (i!=imageIdx) {
                            images.push(product.images[i]);
                        }
                    }

                    product.images = images;
                }

                renderImages();
            });

            $('.description-images-add').append(d);
            counter++;
        }
    });

    matchImagesWithExtra();
});

$(document).on('click', '#modal-add-image .add-var-image, #modal-upload-image .add-var-image', function (e) {
    var src = $(this).attr('src');
    if (src.indexOf('?') === -1) {
        src = src + '?ext';
    }

    var imageIdx = indexOfImages(product.images, src);
    if (imageIdx == -1) {
        product.images.push(src);
    } else {
        var images = [];

        for (var i = 0; i < product.images.length; i++) {
            if (i!=imageIdx) {
                images.push(product.images[i]);
            }
        }

        product.images = images;
    }

    renderImages();
});

$('.shipping-tab').click(function (e) {
    var iframe = $('#tab-3').find('iframe');
    if (iframe.attr('src') && iframe.attr('src').length) {
        return;
    }

    iframe.attr('src', iframe.attr('data-src'));
});

$('.original-tab').click(function (e) {
    var iframe = $('#tab-2 .original-description iframe');
    if (iframe.attr('src') && iframe.attr('src').length) {
        return;
    }

    iframe.attr('src', iframe.attr('data-src'));
});

$('form#product-config-form').submit(function (e) {
    e.preventDefault();

    var data = $(this).serialize();

    $.ajax({
        url: '/api/fb/product-config',
        type: 'POST',
        data: data,
        context: {form: $(this)},
        success: function (data) {
            if (data.status == 'ok') {
                toastr.success('Saved.','User Config');

            } else {
                displayAjaxError('Product Config', data);
            }
        },
        error: function (data) {
            displayAjaxError('Product Config', data);
        },
        complete: function () {
        }
    });

    return false;
});

function indexOfImages(images, link) {
    for (var i = images.length - 1; i >= 0; i--) {
        if(cleanImageLink(images[i]) == cleanImageLink(link)) {
            return i;
        }
    }

    return -1;
}

function renderImages() {
    $('#var-images').empty();

    $.each(product.allImages, function (i, el) {

        var d = $('<div>', {
            'class': 'var-image-block',
            'image-url': el
        });

        var imageId = 'product-image-' + i;

        var img = $('<img>', {
            src: el,
            'id': imageId,
            'class': 'var-image',
            'image-url': el,
            'image-id': i,
            'style': 'cursor: default'
        });

        d.append(img);

        d.append($('<div>', {
            'class': "loader",
            'html': '<i class="fa fa-spinner fa-spin fa-2x"></i>'
        }));

        var buttons = [];
        buttons.push($('<button>', {
            'title': "Delete",
            'class': "btn btn-danger btn-xs itooltip image-delete",
            'html': '<i class="fa fa-times"></i>'
        }));

        buttons.push($('<a>', {
            'title': "Download",
            'class': "btn btn-info btn-xs itooltip download-image",
            'href': el,
            'download': i + '-' + cleanImageLink(el).split('/').pop(),
            'html': '<i class="fa fa-download"></i>'
        }));

        if (config.clipping_magic.clippingmagic_editor) {
            buttons.push($('<button>', {
                'title': "Remove Background",
                'class': "btn btn-warning btn-xs itooltip remove-background-image-editor",
                'html': '<i class="fa fa-scissors"></i></button>'
            }));
        }

        if (config.photo_editor) {
            buttons.push($('<button>', {
                'title': "Simple Editor",
                'class': "btn btn-primary btn-xs itooltip edit-photo",
                'html': '<i class="fa fa-edit"></i>',
                'data-image-id': i
            }));
        }

        if (config.advanced_photo_editor) {
            buttons.push($('<button>', {
                'title': "Advanced Editor",
                'class': "btn btn-warning btn-xs itooltip advanced-edit-photo",
                'html': '<i class="fa fa-picture-o"></i></a>'
            }));
        }

        $.each(buttons, function (i, el) {
            d.append(el.css({
                right: (i * 27) + 'px'
            }));
        });

        d.find('.image-delete').click(imageClicked);

        d.find('.edit-photo').click(function (e) {
            var image = $(this).parents('.var-image-block').find('img')[0];
            launchEditor(image);
        });

        d.find('.remove-background-image-editor').click(function(e) {
            e.preventDefault();

            initClippingMagic($(this));
        });

        d.mouseenter(function() {
            $(this).find('button').show();
            $(this).find('.advanced-edit-photo').show();
            $(this).find('.download-image').show();
        })
        .mouseleave(function() {
            $(this).find('button').fadeOut();
            $(this).find('.advanced-edit-photo').fadeOut();
            $(this).find('.download-image').fadeOut();
        });

        $('#var-images').append(d);
    });

    matchImagesWithExtra();

    $('#var-images .itooltip').bootstrapTooltip({
        container: 'body'
    });
}

$('#download-fb-images').on('click', function(e) {
    e.preventDefault();

    function urlToPromise(url) {
        return new Promise(function(resolve, reject) {
            JSZipUtils.getBinaryContent(url, function(err, data) {
                if (err) {
                    reject(err);
                } else {
                    resolve(data);
                }
            });
        });
    }

    var zip = new JSZip();
    $.each(product.allImages, function (i, src) {
        var filename = i + '-' + src.split('/').pop().split('?')[0];

        zip.file(filename, urlToPromise(src), {
            binary: true
        });
    });

    zip.generateAsync({type: 'blob'}).then(function(blob) {
        saveAs(blob, 'product-images-' + config.product_id + '.zip');
    });
});

function launchEditor(image) {
    if (config.photo_editor !== null) {
        feather_editor.launch({'image': image});
    } else {
        swal('Image Editor', 'Please upgrade your plan to use this feature.', 'warning');
    }
}

$('.add-images-btn').click(function (e) {
    e.preventDefault();

    if ($('#modal-add-image img').length) {
        $('#modal-add-image').modal('show');
    } else {
        window.extensionSendMessage({
            subject: 'getImages',
            from: 'webapp',
            url: $(e.target).attr('original-product'),
            cache: true,
        }, function (images) {
            if (images && images.length) {
                $.each(images, function (i, el) {
                    var img_el = '<div class="col-xs-3 add-var-image-block"><img src="'+ el +'" class="add-var-image unveil" /></div>';
                    $('#modal-add-image #images-row').append(img_el);
                });

                $('#modal-add-image').modal('show');
            }
        });
    }
});

$('#modal-add-image').on('shown.bs.modal', function() {
    $('#modal-add-image img').trigger("unveil");
});

document.renderImages = renderImages;
var export_template = Handlebars.compile($("#product-export-template").html());
Handlebars.registerHelper('urlencode', function(text) {
    return encodeURIComponent(text).replace(/%20/g, '+');
});

// Product Shopify Connect
window.fbProductSelected = function (store, fb_id) {
    $.ajax({
        url: api_url('product-connect', 'fb'),
        type: 'POST',
        data: {
            product: config.product_guid,
            fb: fb_id,
            store: store
        },
        success: function (data) {
            $('#modal-fb-product').modal('hide');
            window.location.hash = 'connections';
            window.location.reload();
        },
        error: function (data) {
            displayAjaxError('Connect Product', data);
        }
    });
};

$('.product-connection-change').click(function (e) {
    e.preventDefault();

    $('#modal-fb-product').modal('show');
});

$('.product-connection-disconnect').click(function (e) {
    e.preventDefault();

    swal({
        title: "Disconnect Product",
        text: "Are you sure you want to disconnect this product?",
        type: "warning",
        showCancelButton: true,
        closeOnCancel: true,
        closeOnConfirm: false,
        confirmButtonColor: "#DD6B55",
        confirmButtonText: "Disconnect",
        cancelButtonText: "Cancel"
    },
    function(isConfirmed) {
        if (isConfirmed) {
            $.ajax({
                url: api_url('product-connect', 'fb') + '?' + $.param({
                    product: config.product_guid,
                }),
                type: 'DELETE',
                success: function (data) {
                    window.location.hash = 'connections';
                    window.location.reload();
                },
                error: function (data) {
                    displayAjaxError('Connect Product', data);
                }
            });
        }
    });
});

$('.remove-background-image-editor').click(function(e) {
    e.preventDefault();

    initClippingMagic($(this));
});

$('tr.fb-variant [name="compare_at_price"]').on('blur', function() {
    var compare_price = $(this).val();
    var productPrice = $(this).parents('tr.fb-variant').find('[name="price"]').val();
    if (compare_price != '' && compare_price < productPrice) {
        $(this).val('');
        toastr.warning(' Compare at price should be greater than Price');
        $(this).css("border", "1px solid red");
    }
    });

function initClippingMagic(el) {

    var image = $(el).siblings('img');
    if (!config.clipping_magic.clippingmagic_editor) {
        swal('Clipping Magic', "You haven't subscribe for this feature", 'error');
        return;
    }

    $.ajax({
        url: '/api/clippingmagic-clean-image',
        type: 'POST',
        data: {
            image_url: image.attr('src'),
            product_id: config.product_id,
            action: 'edit',
        }
    }).done(function(data) {
        clippingmagicEditImage(data, image);
    }).fail(function(data) {
        if (data.status == 402) {
            swal({
                title: 'Clipping Magic Credits',
                text: 'Looks like your credits have run out.\nClick below to add more credits.',
                type: "warning",
                animation: false,
                showCancelButton: true,
                closeOnCancel: true,
                closeOnConfirm: true,
                confirmButtonColor: "#93c47d",
                confirmButtonText: "Add Credits",
                cancelButtonText: "No Thanks"
            },
            function(isConfirmed) {
                if (isConfirmed) {
                    window.onbeforeunload = function(e) {
                      return true;
                    };

                    setTimeout(function() {
                        window.location.href = '/user/profile#billing';
                    }, 500);
                }
            });
        } else {
            displayAjaxError('Clipping Magic', data);
        }
    });
}

function clippingmagicEditImage(data, image) {
    var errorsArray = ClippingMagic.initialize({
        apiId: parseInt(data.api_id, 10)
    });

    if (errorsArray.length > 0) {
        swal('Clipping Magic', "Your browser is missing some required features:\n\n" +
            errorsArray.join("\n "), 'error');
    }

    image.siblings(".loader").show();
    ClippingMagic.edit({
        "image": {
            "id": parseInt(data.image_id, 10),
            "secret": data.image_secret
        },
        "locale": "en-US"
    }, function(response) {
        if (response.event == 'result-generated') {
            $.ajax({
                url: '/api/clippingmagic-clean-image',
                type: 'POST',
                data: {
                    image_id: response.image.id,
                    product: config.product_id,
                    action: 'done',
                }
            }).done(function(data) {
                $.ajax({
                    url: '/upload/save_image_s3',
                    type: 'POST',
                    data: {
                        product: config.product_id,
                        url: data.image_url,
                        old_url: image.attr('src'),
                        clippingmagic: true,
                        fb: 1
                    }
                }).done(function(data) {
                    image.attr('src', data.url).siblings(".loader").hide();
                    product.images[parseInt(image.attr('image-id'), 10)] = data.url;
                }).fail(function(data) {
                    displayAjaxError('Clipping Magic', data);
                });
            }).fail(function(data) {
                displayAjaxError('Clipping Magic', data);
            });
        } else {
            image.siblings(".loader").hide();
            swal('Clipping Magic', response.error.message, 'error');
        }
    });
}

function allVariantsAreSelected() {
    var allVariantsSelected = true;

    $('#fb-variants tr.fb-variant').each(function(j, tr) {
        if (!$('[name="variant-selected"]', tr).prop('checked')) {
            allVariantsSelected = false;
            return false;
        }
    });

    return allVariantsSelected;
}

function atLeastOneVariantIsSelected() {
    var atLeastOneVariantSelected = false;

    $('#fb-variants tr.fb-variant').each(function(j, tr) {
        if ($('[name="variant-selected"]', tr).prop('checked')) {
            atLeastOneVariantSelected = true;
            return false;
        }
    });
    return atLeastOneVariantSelected;
}

$('#bulk-edit-variants-btn').on('click', function(e) {
    e.preventDefault();

    if (!atLeastOneVariantIsSelected()) {
        swal('Bulk Edit Variants', 'Please select at least one variant to edit', 'error');
        return;
    }

    // Elements
    var weightUnit = $('#variant-weight-unit');

    // Uncheck all checkboxes
    $('#modal-fb-variants-edit-form input.variant-editable-field[type=checkbox]').each(function(i, el) {
        $(el).prop('checked', false);
    });

    // Clear and disable all inputs
    $('#modal-fb-variants-edit-form input.form-control').each(function(i, el) {
        $(el).val('');
        $(el).prop('disabled', true);
    });

    // Disable all inputs
    weightUnit.val('g');
    weightUnit.prop('disabled', true);

    $('#modal-fb-variants-edit-form').modal('show');
});

$('#modal-fb-variants-edit-form #save-changes').on('click', function() {
    var fields = {
        price: {
            enabled: $('#edit-price-checkbox').prop('checked'),
            value: $('#variant-price').val(),
        },
        compareatprice: {
            enabled: $('#edit-compare-at-checkbox').prop('checked'),
            value: $('#variant-compare-at').val(),
        },
        stock: {
            enabled: $('#edit-stock-checkbox').prop('checked'),
            value: $('#variant-stock').val(),
        },
        weight: {
            enabled: $('#edit-weight-checkbox').prop('checked'),
            value: $('#variant-weight').val(),
        },
        weightunit: {
            enabled: $('#edit-weight-unit-checkbox').prop('checked'),
            value: $('#variant-weight-unit').val(),
        }
    };

    // Update values of enabled fields for each selected variant
    $('#fb-variants tr.fb-variant').each(function(j, tr) {
        if ($('[name="variant-selected"]', tr).prop('checked')) {
            Object.keys(fields).forEach(function(fieldName) {
                if (fields[fieldName].enabled) {
                    $('[name="' + fieldName + '"]', tr).val(fields[fieldName].value);
                }
            });
        }
    });

    $('#modal-fb-variants-edit-form').modal('hide');
});

$('#edit-price-checkbox').on('click', function() {
    $('#variant-price').prop('disabled', !$(this).prop('checked'));
});

$('#edit-compare-at-checkbox').on('click', function() {
    $('#variant-compare-at').prop('disabled', !$(this).prop('checked'));
});
$('#edit-stock-checkbox').on('click', function() {
    $('#variant-stock').prop('disabled', !$(this).prop('checked'));
});

$('#edit-weight-checkbox').on('click', function() {
    $('#variant-weight').prop('disabled', !$(this).prop('checked'));
});

$('#edit-weight-unit-checkbox').on('click', function() {
    $('#variant-weight-unit').prop('disabled', !$(this).prop('checked'));
});

$('#all-variants-select-checkbox').on('click', function() {
    var selectAllCheckbox = $(this);

    // Update each variant's checkbox value to match the "Select All" checkbox's value
    $('#fb-variants tr.fb-variant').each(function(j, tr) {
        $('[name="variant-selected"]', tr).prop('checked', selectAllCheckbox.prop('checked'));
    });
});

$('.variant-checkbox').on('click', function() {
    // When a single row gets checked/unchecked, update the "Select All" checkbox's value
    $('#all-variants-select-checkbox').prop('checked', allVariantsAreSelected());
});

(function() {
    showProductInfo(product);
    if (product.status !== 'active') {
        productErrorLog();
    }

    setTimeout(function() {
        var element = document.querySelector("#trix-notes");
        element.editor.setSelectedRange([0, 0]);
        element.editor.insertHTML(config.product_notes);

        if (typeof(Pusher) === 'undefined') {
            toastr.error('This could be due to using Adblocker extensions<br>' +
                'Please whitelist Dropified App website and reload the page<br>' +
                'Contact us for further assistance',
                'Pusher service is not loaded', {timeOut: 0, extendedTimeOut: 0});
        }
    }, 1000);

    $(".tag-it").tagit({
        allowSpaces: true,
        autocomplete: {
            source: '/autocomplete/tags',
            delay: 500,
            minLength: 1
        }
    });

    $.each(config.exports, function () {
        $('#export-container').append(export_template(this));
    });

    bindExportEvents();

    $('#var-images').on('click', '.download-image', function(e) {
        // The download attribute only works for files with same origin
        // Alternative way is to fetch and send as blob
        if ($(this).get(0).hostname !== window.document.location.hostname) {
            e.preventDefault();

            var href = $(this).attr('href'),
                fileName = $(this).attr('download'),
                imgElement = document.createElement('a');

            imgElement.href = href;
            imgElement.download = fileName;

            fetch(href).then(function(response) {
                return response.blob();
            }).then(function(blob) {
                imgElement.href = window.URL.createObjectURL(blob);
                imgElement.click();
            }).catch(function(err) {
                imgElement.target = '_blank';
                imgElement.click();
            });
        }
    });

    // if (variants.length < 2) {
    // TODO: enable variants modification once it's implemented
    $('#advanced_variants').prop('checked', true);
    showAdvancedVariantsView();
    // }
})();
})(config, product, variants, variantsConfig, productDetails);
