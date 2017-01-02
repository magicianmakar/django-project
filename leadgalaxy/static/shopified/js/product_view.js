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
                api_data.product.options.push({
                    'name': $(el).find('#product-variant-name').val(),
                    'values': vals
                });
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

                        if (product.variants_sku && product.variants_sku.hasOwnProperty(vars_list[i])) {
                            vdata["sku"] = product.variants_sku[vars_list[i]];
                        }
                    } else {
                        var sku = [];

                        $.each(vars_list[i], function (j, va) {
                            vdata["option"+(j+1)] = va;

                            if (product.variants_sku && product.variants_sku.hasOwnProperty(va)) {
                                sku.push(product.variants_sku[va]);
                            }
                        });

                        if (sku.length) {
                            vdata["sku"] = sku.join(';');
                        }
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
    if (config.shopify_options === null) {
        var targetVariants = product.variants.filter(function(v) { return v.title === val; });
        if (targetVariants.length > 0) {
            $('#split-variants-count').text(targetVariants[0].values.length);
            $('#split-variants-values').text(targetVariants[0].values.join(', '));
        }
    } else {
        var targetVariants = config.shopify_options.filter(function(o) { return o.name === val; });
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
        url: '/api/product-split-variants',
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
                if ($('#export-btn').attr('target') === 'shopify-update') {
                  toastr.success('The variants are splitted into new products now.\r\nThe new products will get connected to shopify very soon.', 'Product Split!');
                } else {
                  toastr.success('The variants are splitted into new products now.', 'Product Split!');
                }
                setTimeout(function() { window.location.href = '/product'; }, 500);
            }
        },
        error: function (data) {
            this.btn.bootstrapBtn('reset');

            displayAjaxError('Split variants into separate products', data);
        }
    });

    $('#modal-pick-variant').modal('hide');
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

    $('.product-original-link', target).bindWithDelay('keyup', function (e) {

        var input = $(e.target);
        var parent = input.parents('.export');
        var product_url = input.val().trim();

        if(!product_url.length || !(/aliexpress.com/i).test(product_url)) {
            return;
        }

        var product_id = product_url.match(/[\/_]([0-9]+)\.html/);
        if(product_id.length != 2) {
            return;
        } else {
            product_id = product_id[1];
        }

        $('.product-original-link-loading', parent).show();

        window.extensionSendMessage({
            subject: 'ProductStoreInfo',
            product: product_id,
        }, function(rep) {
            $('.product-original-link-loading', parent).hide();

            if (rep && rep.name) {
                $('.product-supplier-name', parent).val(rep.name);
                $('.product-supplier-link', parent).val(rep.url);
            }
        });
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

$('form#product-config-form').submit(function (e) {
    e.preventDefault();

    var data = $(this).serialize();

    $.ajax({
        url: '/api/product-config',
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

    if (config.advanced_photo_editor) {
        // Pixlr Doesn't redirect to this page
        pixlr.settings.exit = window.location.origin + '/pixlr/close';
        pixlr.settings.method = 'POST';
        pixlr.settings.referrer = 'Shopified App';
        // setting to false saves the image but doesn't run the redirect script on pixlr.html
        pixlr.settings.redirect = false;
    }

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

        if (config.clipping_magic && config.clipping_magic.clippingmagic_editor) {
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
                'html': '<i class="fa fa-edit"></i>'
            }));
        }

        if (config.advanced_photo_editor) {
            var hash = UUIDjs.create().hex.split('-').join(''),
                imageUrl = el;

            if (!imageUrl.match(/shopifiedapp\.s3\.amazonaws\.com/)) {
                imageUrl = window.location.origin + '/pixlr/serve?' + $.param({image: imageUrl});
            }

            var pixlrUrl = pixlr.url({
                image: imageUrl,
                title: imageId,
                target: window.location.origin + '/upload/save_image_s3?' + $.param({
                    key: hash,
                    product: config.product_id,
                    advanced: true,
                    image_id: imageId
                })
            });

            buttons.push($('<a>', {
                'title': "Advanced Editor",
                'class': "btn btn-warning btn-xs itooltip advanced-edit-photo",
                'target': "_blank",
                'href': pixlrUrl,
                'data-hash': hash,
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
            var img = $(this).parents('.var-image-block').find('img');

            launchEditor(
                img.attr('id'),
                img.attr('src')
            );
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
        config.feather_editor.launch({
            image: id,
            url: src
        });
        return false;
    } else {
        swal('Image Editor', 'Please upgrade your plan to use this feature.', 'warning');
    }
}

$('#download-images').on('click', function(e) {
    e.preventDefault();

    var btn = $(e.target);
    btn.bootstrapBtn('loading');

    $.ajax({
        url: $(this).attr('href'),
        type: 'get',
        dataType: 'json',
        success: function(result) {
            window.location = result.url;
        },
        error: function(data) {
            displayAjaxError('Images Download', data);
        },
        complete: function () {
            btn.bootstrapBtn('reset');
        }
    });
});

$('#var-images').on('click', '.var-image-block .advanced-edit-photo', function(e) {
    if (config.advanced_photo_editor) {
        var image = $(this).siblings('img'),
            imageUrl = image.attr('src'),
            imageId = image.attr('id'),
            imageHash = $(this).attr('data-hash');

        if (!imageUrl.match(/shopifiedapp\.s3\.amazonaws\.com/)) {
            imageUrl = window.location.origin + '/pixlr/serve?' + $.param({image: image.attr('src')});
        }

        $.ajax({
            type: 'GET',
            url: '/api/pixlr-hash',
            data: {'new': imageId, 'random_hash': imageHash},
            success: function(result) {
                if (result.status == 'new') {
                    pixlrCheck(imageHash);
                } else {
                    displayAjaxError('Advanced Image Editor', result);
                }
            },
            error: function(result) {
                displayAjaxError('Advanced Image Editor', result);
            }
        });
    } else {
        e.preventDefault();
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
                    if (document.pixlrPopup) {
                        document.pixlrPopup.close();
                    }
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
Handlebars.registerHelper('urlencode', function(text) {
    return encodeURIComponent(text).replace(/%20/g, '+');
});

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
