/* global $, config, toastr, swal, product:true, renderImages, allPossibleCases */
/* global setup_full_editor, cleanImageLink */

(function(config, product) {
'use strict';

var image_cache = {};

function showProductInfo(rproduct) {
    product = rproduct;
    if (product) {
        $('#product-title').val(product.title);
        $('#product-price').val(product.price);
        $('#product-type').val(product.type);
        $('#product-tag').val(product.tags);
        $('#product-vendor').val(product.vendor);
        $('#product-compare-at').val(product.compare_at_price);

        if (product.variants.length && !config.connected) {
            $.each(product.variants, function(i, el) {
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

        if (product.weight) {
            $('#product-weight').val(product.weight);
        }

        if (product.description) {
            document.editor.setData(product.description);
        }

        renderImages();
    }
}

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

    $(this).parent().remove();
}

$('#product-export-btn').click(function (e) {
    e.preventDefault();

    var btn = $(this);

    productSave($('#product-save-btn'), function () {
        productExport(btn);
    });
});

function productExport(btn) {
    var store_id = $('#store-select').val();
    if (!store_id || store_id.length === 0) {
        swal('Product Export', 'Please choose a Shopify store first!', 'error');
        return;
    }

    btn.bootstrapBtn('loading');

    $.ajax({
        url: api_url('product-export', 'chq'),
        type: 'POST',
        data: {
            'product': config.product_id,
            'store': store_id,
        },
        context: {btn: btn},
        success: function (data) {
            var pusher = new Pusher(config.sub_conf.key);
            var channel = pusher.subscribe(config.sub_conf.channel);

            channel.bind('product-export', function(data) {
                console.dir(data);

                if (data.product == config.product_id) {
                    if (data.progress) {
                        btn.text(data.progress);
                        return;
                    }

                    btn.bootstrapBtn('reset');

                    pusher.unsubscribe(config.sub_conf.channel);

                    if (data.success) {
                        toastr.success('Product Exported.','CommerceHQ Export');

                        setTimeout(function () {
                            window.location.reload();
                        }, 1500);
                    } else {
                        displayAjaxError('CommerceHQ Export', data);
                    }
                }
            });
        },
        error: function (data) {
            $(this.btn).bootstrapBtn('reset');
            displayAjaxError('Product Export', data);
        }
    });
}

$('#product-update-btn').click(function (e) {
    e.preventDefault();

    var btn = $(this);
    btn.bootstrapBtn('loading');

    var api_data = {
        'title': $('#product-title').val().trim(),
        'type': $('#product-type').val(),
        'tags': $('#product-tag').val(),
        'vendor': $('#product-vendor').val(),
        'published': $('#product-visible').prop('checked'),

        'price': parseFloat($('#product-price').val()),
        'compare_price': parseFloat($('#product-compare-at').val()),

        'weight': parseFloat($('#product-weight').val()),
        'weight_unit': $('#product-weight-unit').val(),

        'description': document.editor.getData(),

        'variants': [],
        'images': product.images,
    };

    if (product.is_multi) {
        $('#commercehq-variants tr.commercehq-variant').each(function(j, tr) {

            var variant_data = {
                id: parseInt($(tr).attr('variant-id'))
            };

            var attrs = [
                'price', 'compare_price', 'sku'
            ];

            $.each(attrs, function(k, att) {
                var att_val = $('[name="' + att + '"]', tr).val();
                if (att_val && att_val.length > 0) {
                    if (k < 2) {
                        att_val = parseFloat(att_val);
                    }

                    variant_data[att] = att_val;
                } else {
                    variant_data[att] = '';
                }
            });

            api_data.variants.push(variant_data);
        });
    }

    $.ajax({
        url: api_url('product-update', 'chq'),
        type: 'POST',
        data: JSON.stringify ({
            'product': config.product_id,
            'data': JSON.stringify(api_data),
        }),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        context: {btn: btn},
        success: function (data) {
            var pusher = new Pusher(config.sub_conf.key);
            var channel = pusher.subscribe(config.sub_conf.channel);

            channel.bind('product-update', function(data) {
                console.dir(data);

                if (data.product == config.product_id) {
                    if (data.progress) {
                        btn.text(data.progress);
                        return;
                    }

                    btn.bootstrapBtn('reset');

                    pusher.unsubscribe(config.sub_conf.channel);

                    if (data.success) {
                        toastr.success('Product Updated.','CommerceHQ Update');
                        setTimeout(function () {
                            window.location.reload();
                        }, 1500);
                    } else {
                        displayAjaxError('CommerceHQ Update', data);
                    }
                }
            });
        },
        error: function (data) {
            displayAjaxError('Save Product', data);
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
    var targetVariants = [];

    if (config.commercehq_options === null) {
        targetVariants = product.variants.filter(function(v) { return v.title === val; });
        if (targetVariants.length > 0) {
            $('#split-variants-count').text(targetVariants[0].values.length);
            $('#split-variants-values').text(targetVariants[0].values.join(', '));
        }
    } else {
        targetVariants = config.commercehq_options.filter(function(o) { return o.title === val; });
        if (targetVariants.length > 0) {
            $('#split-variants-count').text(targetVariants[0].values.length);
            $('#split-variants-values').html(targetVariants[0].values.join('<br />'));
        }
    }
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
        url: api_url('product-split-variants', 'chq'),
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
                if ($('#product-export-btn').attr('target') === 'product-update') {
                  toastr.success('The variants are splitted into new products now.\r\n' +
                    'The new products will get connected to shopify very soon.', 'Product Split!');
                } else {
                  toastr.success('The variants are splitted into new products now.', 'Product Split!');
                }
                setTimeout(function() { window.location.href = '/chq/products'; }, 500);
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
    var btn = $(this);
    productSave(btn, function () {
        toastr.success('Product changes saved!','Product Saved');
    });

});

function productSave(btn, callback) {
    var target = btn.attr('target');

    btn.bootstrapBtn('loading');

    var store_id = $('#store-select').val();

    var api_data = {
        'title': $('#product-title').val().trim(),
        'description': document.editor.getData(),
        'price': parseFloat($('#product-price').val()),
        'compare_at_price': parseFloat($('#product-compare-at').val()),
        'images': product.images,
        'original_url': product.original_url,
        'type': $('#product-type').val(),
        'tags': $('#product-tag').val(),
        'vendor': $('#product-vendor').val(),
        'weight': parseFloat($('#product-weight').val()),
        'weight_unit': $('#product-weight-unit').val(),
        'published': $('#product-visible').prop('checked'),

        'variants': []
    };

    if ($('#variants .variant').length) {
        $('#variants .variant').each(function (i, el) {
            api_data.variants.push({
                'title': $(el).find('#product-variant-name').val(),
                'values': $(el).find('#product-variant-values').val().split(',')
            });

        });
    }

    $.ajax({
        url: api_url('product-save', 'chq'),
        type: 'POST',
        data: JSON.stringify ({
            'product': config.product_id,
            'store': store_id,
            'data': JSON.stringify(api_data),
        }),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        context: {btn: btn},
        success: function (data) {
            if (callback) {
                callback();
            }
        },
        error: function (data) {
            displayAjaxError('Save Product', data);
        },
        complete: function () {
            $(this.btn).bootstrapBtn('reset');
        }
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

    var product_id = $(this).attr('product-id');

    $(this).bootstrapBtn('loading');

    $.ajax({
        url: api_url('product-duplicate', 'chq'),
        type: 'POST',
        data: {
            product: product_id
        },
        context: {btn: $(this)},
        success: function (data) {
            var btn = this.btn;
            btn.bootstrapBtn('reset');

            if ('product' in data) {
                btn.attr('href', data.product.url);
                toastr.success('Duplicate Product.','Product Duplicated!');

                setTimeout(function() {
                    btn.html('<i class="fa fa-external-link"></i> Open duplicate');
                }, 100);

                window.open(data.product.url, '_blank');
            }
        },
        error: function (data) {
            this.btn.bootstrapBtn('reset');
        }
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
    var imageID = $(this).parent().find('img').attr('image-id');
    var new_images = [];

    for (var i = 0; i < product.images.length; i++) {
        if (i != imageID) {
            new_images.push(product.images[i]);
        }
    }

    product.images = new_images;
    $(this).parent().remove();

    // Remove remaining "Delete" tooltip
    $('.tooltip').remove();

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
        url: api_url('product-notes', 'chq'),
        context: btn,
        data: {
            'notes': $('#product-notes').val(),
            'product': config.product_id,
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
        product: config.product_id
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

    $('.export-save-btn', target).click(function (e) {
        e.preventDefault();

        var btn = $(this);
        var form = $(this).parents('.product-export-form');

        btn.bootstrapBtn('loading');

        $.ajax({
            type: 'POST',
            url: api_url('supplier', 'chq'),
            context: btn,
            data: {
                'original-link': $('.product-original-link', form).val(),
                'shopify-link': $('.product-shopify-link', form).val(),
                'supplier-name': $('.product-supplier-name', form).val(),
                'supplier-link': $('.product-supplier-link', form).val(),
                'product': form.data('product-id'),
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
            url: api_url('supplier-default', 'chq'),
            context: btn,
            data: {
                'product': form.data('product-id'),
                'export': form.data('export-id'),
            },
            success: function(data) {
                toastr.success('Default Supplier Changed.','Product Connections');

                setTimeout(function() {
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
                    url: api_url('supplier', 'chq') + '?' + $.param({
                        'product': form.data('product-id'),
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

$('#modal-add-image .add-var-image').click(function (e) {
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

$('.product-alerts-tab').click(function () {
    if ($(this).prop('loaded') !==  true) {
        $('.product-alerts-loading i').addClass('fa-spin');
        $('.product-alerts-loading').show();

        var url = '/chq/products/update?product=' + $(this).attr('product-id');
        if ($(this).prop('page')) {
            url = url + '&page=' + $(this).prop('page');
        }

        $('.product-alerts').load(url,
            function() {
                $('.product-alerts-tab').prop('loaded', true);

                $('.product-alerts-loading i').removeClass('fa-spin');
                $('.product-alerts-loading').hide();

                $('.pagination a').click(function (e) {
                    e.preventDefault();

                    var page = getQueryVariable('page', $(this).prop('href'));
                    if (page) {
                        $('.product-alerts-tab').prop('page', page);
                        $('.product-alerts-tab').prop('loaded', false);

                        $('.product-alerts-tab').trigger('click');
                    }
                });
            }
        );
    }
});

$('form#product-config-form').submit(function (e) {
    e.preventDefault();

    var data = $(this).serialize();

    $.ajax({
        url: '/api/chq/product-config',
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
        if(cleanImageLink(images[i]).toLocaleLowerCase() == cleanImageLink(link).toLocaleLowerCase()) {
            console.log('Lower issue',cleanImageLink(images[i]), cleanImageLink(link));
        }
    }

    return -1;
}

function renderImages() {
    $('#var-images').empty();

    $.each(product.images, function (i, el) {
        if (i !== 0 && i % 4 === 0) {
            $('#var-images').append($('<div class="col-xs-12"></div>'));
        }

        var d = $('<div>', {
            'class': 'col-xs-3 var-image-block',
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
            var imageUrl = createPhotopeaURL(el, imageId);

            buttons.push($('<a>', {
                'title': "Advanced Editor",
                'class': "btn btn-warning btn-xs itooltip advanced-edit-photo",
                'target': "_blank",
                'href': imageUrl,
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

function launchEditor(id, src) {
    if (config.photo_editor !== null) {
        feather_editor.launch({'image': image});
    } else {
        swal('Image Editor', 'Please upgrade your plan to use this feature.', 'warning');
    }
}

var PusherSubscription = {
    init: function() {
        if (!window.pusher || !window.channel) {
            window.pusher = new Pusher(config.sub_conf.key);
            window.channel = window.pusher.subscribe(config.sub_conf.channel);
        }
    },
    imagesDownload: function() {
        this.init();

        window.channel.bind('images-download', function(data) {
            if (data.product == config.product_id) {
                $('#download-images').bootstrapBtn('reset');

                if (data.success) {
                    setTimeout(function() {
                        window.location.href = data.url;
                    }, 500);
                } else {
                    displayAjaxError('Images Download', data);
                }
            }
        });
    }
};

$('#download-images').on('click', function(e) {
    e.preventDefault();

    PusherSubscription.imagesDownload();

    var btn = $(e.target);
    btn.bootstrapBtn('loading');

    $.ajax({
        url: api_url('product-image-download', 'chq'),
        type: 'GET',
        data: {
            product: btn.attr('product')
        },
        success: function(result) {
        },
        error: function(data) {
            displayAjaxError('Images Download', data);
        }
    });
});

$('.add-images-btn').click(function (e) {
    e.preventDefault();

    $('#modal-add-image').modal('show');
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
window.commercehqProductSelected = function (store, chq_id) {
    $.ajax({
        url: api_url('product-connect', 'chq'),
        type: 'POST',
        data: {
            product: config.product_id,
            shopify: chq_id,
            store: store
        },
        success: function (data) {
            $('#modal-commercehq-product').modal('hide');
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

    $('#modal-commercehq-product').modal('show');
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
                url: api_url('product-connect', 'chq') + '?' + $.param({
                    product: config.product_id,
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
                        chq: 1
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

(function() {
    setup_full_editor('product-description');

    showProductInfo(product);

    setTimeout(function() {
        var element = document.querySelector("#trix-notes");
        element.editor.setSelectedRange([0, 0]);
        element.editor.insertHTML(config.product_notes);

        if (typeof(Pusher) === 'undefined') {
            toastr.error('This could be due to using Adblocker extensions<br>' +
                'Please whitelist Dropified website and reload the page<br>' +
                'Contact us for further assistance',
                'Pusher service is not loaded', {timeOut: 0, extendedTimeOut: 0});
        }
    }, 2000);

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

})();
})(config, product);
