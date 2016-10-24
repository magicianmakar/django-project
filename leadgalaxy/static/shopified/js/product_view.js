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

        if (product.variants.length) {
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

        if (config.shopify_images !== null) {
            product.images = [];
            $.each(config.shopify_images, function (i, img) {
                product.images.push(img.src);
            });
        }

        renderImages();
    }
}

$(document).delegate("button#requires_shipping", "click", function(e){
    e.preventDefault();

    $(this).bootstrapBtn('loading');
    $.ajax({
        url: '/api/variant-requires-shipping',
        type: 'POST',
        data: {
            'store': $('#store-select').val(),
            'product': $(this).data('product'),
        },
        success: function (data) {
            window.location.reload();
        },
        error: function (data) {
            $(this.btn).bootstrapBtn('reset');
            displayAjaxError('Shipping Status', data);
        }
    });
});

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

function productExported(data, target, btn) {
    if ('product' in data) {
        if (data.product.data) {
            $('#btn-variants-img').prop('store-id', $('#store-select').val());
            $('#btn-variants-img').prop('product-id', data.product.data.id);
            $('#btn-variants-img').show();
        }

        $("#view-btn").attr("shopify-id", data.product.id);
        $("#view-btn").attr("shopify-url", data.product.url);
        $("#view-btn").show();

        if (target == 'shopify') {
            $('#export-btn, #save-for-later-btn').hide();
            $('#more-options-btn').trigger('click');

            toastr.success('Product Exported.','Shopify Export');
        } else {
            toastr.success('Product Updated in Shopify.','Shopify Update');
            window.location.href = window.location.href;
        }
    }  else {
        displayAjaxError('Product Export', data);
    }

    $(btn).bootstrapBtn('reset');
}

function waitForTask(task_id, target, button) {
    document.taskInterval = setInterval(function () {
        $.ajax({
            url: '/api/export-product',
            type: 'GET',
            data: {id: task_id, count: document.taskCount},
            context: {target: target, btn: button},
            success: function (data) {
                if (data.ready) {
                    clearInterval(document.taskInterval);

                    productExported(data.data, this.target, this.btn);
                }
            },
            error: function (data) {
                clearInterval(document.taskInterval);
                $(this.btn).bootstrapBtn('reset');

                displayAjaxError('Export Error', data);
            },
            complete: function() {
                document.taskCount += 1;
            }
        });
    }, 1000);
}

$('#export-btn').click(function () {
    $('#save-for-later-btn').prop('no-confirm', true).trigger('click');

    var btn = $(this);
    var target = btn.attr('target');

    if (target != 'shopify' && target != 'shopify-update') {
        swal('Unknow target', 'Unknow target', 'error');
        return;
    }

    var store_id = $('#store-select').val();
    if (!store_id || store_id.length === 0) {
        swal('Product Export', 'Please choose a Shopify store first!', 'error');
        return;
    }

    btn.bootstrapBtn('loading');

    var api_data = {
      "product": {
        "title": $('#product-title').val(),
        "body_html": document.editor.getData(),
        "product_type": $('#product-type').val(),
        "vendor": $('#product-vendor').val(),
        "published": $('#product-visible')[0].checked,
        "tags": $('#product-tag').val(),
        "variants": [],
        "options": [],
        "images" :[]
      }
    };

    if (product.images) {
        for (var i = 0; i < product.images.length; i++) {
            var image = {
                src: product.images[i]
            };

            var imageFileName = hashUrlFileName(image.src);
            if (product.variants_images && product.variants_images.hasOwnProperty(imageFileName)) {
                image.filename = 'v-'+product.variants_images[imageFileName]+'__'+imageFileName;
            }

            api_data.product.images.push(image);
        }
    }

    if (config.shopify_options === null) {

        if ($('#variants .variant').length === 0) {
            var vdata = {
                "price": parseFloat($('#product-price').val()),
            };

            if ($('#product-compare-at').val().length) {
                vdata.compare_at_price = parseFloat($('#product-compare-at').val());
            }

            if ($('#product-weight').val().length) {
                vdata.weight = parseFloat($('#product-weight').val());
                vdata.weight_unit = $('#product-weight-unit').val();
            }

            api_data.product.variants.push(vdata);

        } else {
            $('#variants .variant').each(function (i, el) {
                var vals = $(el).find('#product-variant-values').val().split(',');
                if (vals.length>1) {
                    api_data.product.options.push({
                        'name': $(el).find('#product-variant-name').val(),
                        'values': vals
                    });
                }
            });

            var vars_list = [];
            $('#variants .variant').each(function (i, el) {
                var vals = $(el).find('#product-variant-values').val().split(',');
                vars_list.push(vals);
            });

            if (vars_list.length>0) {
                vars_list = allPossibleCases(vars_list);
                for (var i = 0; i < vars_list.length; i++) {
                    var title = vars_list[i].join ? vars_list[i].join(' & ') : vars_list[i];

                    var vdata = {
                        "price": parseFloat($('#product-price').val()),
                        "title": title,
                    };

                    if (typeof(vars_list[i]) == "string") {
                        vdata["option1"] = vars_list[i];
                    } else {
                        $.each(vars_list[i], function (j, va) {
                            vdata["option"+(j+1)] = va;
                        });
                    }

                    if ($('#product-compare-at').val().length) {
                        vdata.compare_at_price = parseFloat($('#product-compare-at').val());
                    }

                    if ($('#product-weight').val().length) {
                        vdata.weight = parseFloat($('#product-weight').val());
                        vdata.weight_unit = $('#product-weight-unit').val();
                    }

                    if (vdata.title in config.shopify_variants) {
                        vdata.id = config.shopify_variants[vdata.title];
                    }

                    api_data.product.variants.push(vdata);
                }
            } else {
                swal('Variants should have more than one value separated by comma (,)');
                btn.bootstrapBtn('reset');
                return;
            }
        }

    } else {
        $('#shopify-variants tr.shopify-variant').each(function(j, tr) {

            var variant_data = {
                id: $(tr).attr('variant-id')
            };

            var attrs = [
                'option1', 'option2', 'option3', 'title', 'weight_unit',
                'price', 'compare_at_price', 'weight'
            ];

            $.each(attrs, function(k, att) {
                var att_val = $('[name="' + att + '"]', tr).val();
                if (att_val && att_val.length > 0) {
                    if (k > 4) {
                        att_val = parseFloat(att_val);
                    }

                    variant_data[att] = att_val;
                }
            });

            api_data.product.variants.push(variant_data);
        });

        api_data.product.options = config.shopify_options;

        // Match images with shopify images
        //api_data.product.images = config.shopify_images;

        var shopify_images_map = {};
        $.each(config.shopify_images, function(i, img) {
            shopify_images_map[img.src] = img;
        });

        var new_images = [];
        $.each(api_data.product.images, function (i, el) {
            if (shopify_images_map.hasOwnProperty(el.src)) {
                new_images.push({
                    id: shopify_images_map[el.src].id
                });
            } else {
                new_images.push(el);
            }
        });

        api_data.product.images = new_images;
    }

    $.ajax({
        url: '/api/' + target,
        type: 'POST',
        data: JSON.stringify ({
            'product': config.product_id,
            'store': store_id,
            'data': JSON.stringify(api_data),
            'b': true,
        }),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        context: {btn: this, target: target},
        success: function (data) {
            if (data.hasOwnProperty('id')) {
                document.taskCount = 1;
                waitForTask(data.id, this.target, this.btn);
            } else {
                productExported(data, this.target, this.btn);
            }
        },
        error: function (data) {
            $(this.btn).bootstrapBtn('reset');

            displayAjaxError('Error', data);
        }

    });
});

$('#save-for-later-btn').click(function (e) {
    var btn = $(this);
    var target = btn.attr('target');

    btn.bootstrapBtn('loading');

    var store_id = $('#store-select').val();

    var api_data = {
        'title': $('#product-title').val(),
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
        url: '/api/' + target,
        type: 'POST',
        data: JSON.stringify ({
            'product': config.product_id,
            'store': store_id,
            'data': JSON.stringify(api_data),
            'b': true,
        }),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        context: {btn: this},
        success: function (data) {
            $(this.btn).bootstrapBtn('reset');

            if ('product' in data) {
                $("#view-btn").attr("shopify-id", data.product.id);
                $("#view-btn").attr("shopify-url", data.product.url);

                if ($('#save-for-later-btn').prop('no-confirm') == true) {
                    $('#save-for-later-btn').prop('no-confirm', false);
                } else {
                    toastr.success('Save for later.','Product Saved');
                }
            }  else {
                displayAjaxError('Save for later', data);
            }
        },
        error: function (data) {
            $(this.btn).bootstrapBtn('reset');
            displayAjaxError('Save for later', data);
        }
    });
});

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
        url: '/api/product-duplicate',
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

    renderImages();
}

$('.var-image-block button').click(imageClicked);

$('.var-image-block').mouseenter(function() {
    $(this).find('button').show();
})
.mouseleave(function() {
    $(this).find('button').fadeOut();
});

$('#btn-variants-img').click(function (e) {
    var store_id = $('#btn-variants-img').prop('store-id');
    var product_id = $('#btn-variants-img').prop('product-id');

    window.location.href = '/product/variants/'+store_id+'/'+product_id;
});

$('#save-product-notes').click(function (e) {
    var btn = $(this);

    btn.bootstrapBtn('loading');

    $.ajax({
        type: 'POST',
        url: '/api/product-notes',
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
            url: '/api/product-metadata',
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
            url: '/api/product-metadata-default',
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
                    url: '/api/product-metadata?' + $.param({
                        'product': form.data('product-id'),
                        'export': form.data('export-id'),
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

        var url = '/products/update?product=' + $(this).attr('product-id');
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

        var img = $('<img>', {
            src: el,
            'id': 'product-image-' + i,
            'class': 'var-image',
            'image-url': el,
            'image-id': i,
            'style': 'cursor: default'
        });
        d.append(img);

        d.append($('<button data-toggle="tooltip" title="Delete Image" class="btn btn-danger ' +
            'btn-xs image-delete" style="display:none;position: absolute;cursor: pointer;' +
            'right: 25px;top: 5px;background-color: rgb(247, 203, 203);color: #B51B18;' +
            'border-radius: 5px;font-weight: bolder;">x</button>'));

        if (config.photo_editor) {
            d.append($('<button data-toggle="tooltip" title="Simple Image Editor" ' +
                'class="btn btn-primary btn-xs edit-photo" style="display:none;' +
                'position:absolute;cursor:pointer;right:50px;top:5px;' +
                'background-color:rgb(226, 255, 228);color: rgb(0, 105, 19);' +
                'border-radius: 5px;font-weight: bolder;">' +
                '<i class="fa fa-edit"></i></button>'));
        }

        if (config.advanced_photo_editor) {
            d.append($('<button data-toggle="tooltip" title="Advanced Image Editor" ' +
                'class="btn btn-warning btn-xs advanced-edit-photo" ' +
                'style="display:none;position:absolute;cursor:pointer;right:80px;'+
                'top:5px;background-color:rgb(255, 245, 195);color:rgb(105, 30, 19);'+
                'border-radius:5px;font-weight:bolder;">' +
                '<i class="fa fa-picture-o"></i></button>'));
        }

        d.find('.image-delete').click(imageClicked);

        d.find('.edit-photo').click(function (e) {
            var img = $(this).parents('.var-image-block').find('img');

            launchEditor(
                img.attr('id'),
                img.attr('src')
            );
        });

        d.mouseenter(function() {
            $(this).find('button').show();
        })
        .mouseleave(function() {
            $(this).find('button').fadeOut();
        });

        $('#var-images').append(d);
    });

    matchImagesWithExtra();
    $('[data-toggle="tooltip"]').bootstrapTooltip();
}

function launchEditor(id, src) {
    if (config.photo_editor !== null) {
        config.feather_editor.launch({
            image: id,
            url: src
        });
        return false;
    } else {
        swal('Image Editor', 'Please upgrade your plan to use this feature.', 'warning');
    }
}

$('#var-images').on('click', '.var-image-block .advanced-edit-photo', function(e) {
    e.preventDefault();
    var image = $(this).siblings('img');
    var imageUrl = image.attr('src');
    var imageId = image.attr('id');

    if (!imageUrl.match(/shopifiedapp\.s3\.amazonaws\.com/)) {
        imageUrl = window.location.origin + '/pixlr/serve?' + $.param({image: image.attr('src')});
    }

    if (config.advanced_photo_editor) {
        $.ajax({
            type: 'GET',
            url: '/api/pixlr-hash',
            data: {'new': imageId},
            success: function(result) {
                if (result.status == 'new') {
                    var pixlrKey = result.key;

                    // Pixlr Doesn't redirect to this page
                    pixlr.settings.exit = window.location.origin + '/pixlr/close';
                    pixlr.settings.method = 'POST';
                    pixlr.settings.referrer = 'Shopified App';
                    // setting to false saves the image but doesn't run the redirect script on pixlr.html
                    pixlr.settings.redirect = false;

                    pixlr.overlay.show({
                        image: imageUrl,
                        title: image.attr('id'),
                        target: window.location.origin + '/upload/save_image_s3?' + $.param({
                            key: pixlrKey,
                            product: config.product_id,
                            advanced: true,
                            image_id:imageId
                        })
                    });

                    pixlrCheck(pixlrKey);
                } else {
                    displayAjaxError('Advanced Image Editor', result);
                }
            },
            error: function(result) {
                displayAjaxError('Advanced Image Editor', result);
            }
        });
    } else {
        swal('Advanced Image Editor', 'Please upgrade your plan to use this feature.', 'warning');
    }
});

$('.add-images-btn').click(function (e) {
    e.preventDefault();

    $('#modal-add-image').modal('show');
});

$('#modal-add-image').on('shown.bs.modal', function() {
    $('#modal-add-image img').trigger("unveil");
});

$('#pixlr-background').click(function(e) {
    e.preventDefault();

    pixlr.overlay.hide();

    clearInterval(document.pixlrInterval);
    document.pixlrInterval = null;
});

function pixlrCheck(key) {
    if (typeof document.pixlrInterval !== 'undefined' || document.pixlrInterval !== null) {
        clearInterval(document.pixlrInterval);
    }

    document.pixlrIntervalCount = 0;
    document.pixlrInterval = setInterval(function() {
        $.ajax({
            type: 'GET',
            url: '/api/pixlr-hash',
            data: {
                check: key,
                count: document.pixlrIntervalCount
            },
            dataType: 'json',
            success: function(result) {
                if (result.status == 'changed') {
                    var image = $('#'+result.image_id);
                    image.attr('src', result.url);
                    product.images[parseInt(image.attr('image-id'), 10)] = result.url;
                    pixlr.overlay.hide();

                    clearInterval(document.pixlrInterval);
                    document.pixlrInterval = null;
                } else {
                    document.pixlrIntervalCount += 1;
                }
            },
            error: function(result) {
                clearInterval(document.pixlrInterval);
                document.pixlrInterval = null;
            }
        });
    }, 3000);
}

document.renderImages = renderImages;
var export_template = Handlebars.compile($("#product-export-template").html());

// Product Shopify Connect
window.shopifyProductSelected = function (store, shopify_id) {
    $.ajax({
        url: '/api/product-connect',
        type: 'POST',
        data: {
            product: config.product_id,
            shopify: shopify_id,
            store: store
        },
        success: function (data) {
            $('#modal-shopify-product').modal('hide');
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

    $('#modal-shopify-product').modal('show');
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
                url: '/api/product-connect?' + $.param({
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

function shopifyProductSearch (e) {
    var loadingContainer = $('#modal-shopify-product .shopify-find-loading');
    var productsContainer = $('#modal-shopify-product .shopify-products');

    var store = $('#modal-shopify-product .shopify-store').val();
    var query = $('#modal-shopify-product .shopify-find-product').val().trim();


    if (!$(this).prop('page')) {
        loadingContainer.show();
        productsContainer.empty();
    } else {
        $(this).bootstrapBtn('loading');
    }

    $.ajax({
        url: '/api/shopify-products',
        type: 'POST',
        data: {
            store: store,
            query: query,
            page: $(this).prop('page')
        },
        context: {
            store: store
        },
        success: function (data) {
            var product_template = Handlebars.compile($("#product-select-template").html());

            if (data.products.length === 0) {
                productsContainer.append($('<div class="text-center"><h3>No Product found with the given search query</h3></div>'));
            }

            var store = this.store;
            $.each(data.products, function () {
                var el = $(product_template({product: this}));

                $('a.shopify-product', el).click(function () {
                    if (window.shopifyProductSelected) {
                        window.shopifyProductSelected(store, $(this).data('product-id'));
                    }
                });

                productsContainer.append(el);
            });

            productsContainer.find('.load-more-btn').remove();

            if (data.next) {
                var moreBtn = $('<button class="btn btn-outline btn-default btn-block ' +
                    'load-more-btn" data-loading-text="<i class=\'fa fa-circle-o-notch fa-spin\'>' +
                    '</i> Loading"><i class="fa fa-plus"></i> Load More</button>');

                moreBtn.prop('page', data.next);
                moreBtn.click(shopifyProductSearch);

                productsContainer.append(moreBtn);
            }
        },
        error: function (data) {
            productsContainer.append($('<div class="text-center"><h3>' +
                'Error occurred while searching for products</h3></div>'));
        },
        complete: function () {
            loadingContainer.hide();
        }
    });
}

$('#modal-shopify-product .shopify-find-product').bindWithDelay('keyup', shopifyProductSearch, 500);
$('#modal-shopify-product .shopify-store').on('change', shopifyProductSearch);
$('#modal-shopify-product .shopify-find-product').trigger('keyup');

(function() {
    setup_full_editor('product-description');

    showProductInfo(product);

    setTimeout(function() {
        var element = document.querySelector("#trix-notes");
        element.editor.setSelectedRange([0, 0]);
        element.editor.insertHTML(config.product_notes);
    }, 2000);

    $(".tag-it").tagit({
        allowSpaces: true
    });

    $.each(config.exports, function () {
        $('#export-container').append(export_template(this));
    });

    bindExportEvents();

})();
})(config, product);
