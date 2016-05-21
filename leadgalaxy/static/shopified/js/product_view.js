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
        "vendor": "",
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
                if (vals.length>1) {
                    vars_list.push(vals);
                }
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
            console.dir(variant_data);
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

            swal('Shopify Export', 'Server error', 'error');
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
                $(el).append($('<img class="extra-added" src="//i.imgur.com/HDg5nrv.png" style="position: absolute;left: 16px;top: 1px;border-radius: 0 0 8px 0;background-color: #fff;">'));
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

$('#save-metadata').click(function (e) {
    var btn = $(this);

    btn.bootstrapBtn('loading');

    $.ajax({
        type: 'POST',
        url: '/api/product-metadata',
        context: btn,
        data: {
            'original-link': cleanUrlPatch($('#product-original-link').val()),
            'shopify-link': $('#product-shopify-link').val(),
            'product': config.product_id,
        },
        success: function(data) {
            if (data.status == 'ok') {
                toastr.success('Modification saved.','Product Metadata');
            } else {
                displayAjaxError('Product Metadata', data);
            }
        },
        error: function(data) {
            displayAjaxError('Product Metadata', data);
        },
        complete: function() {
            btn.bootstrapBtn('reset');
        }
    });
});

$('#modal-add-image').on('show.bs.modal', function (e) {
    $('#modal-add-image .description-images-add').empty();
    var counter=0;
    $('.original-description img').each(function (i, el) {
        if (indexOfImages(config.product_extra_images, $(el).attr('src'))==-1) {
            if (counter % 4 === 0) {
                $('.description-images-add').append($('<div class="col-xs-12"></div>'));
            }

            var d = $('<div>', {'class':'col-xs-3 add-var-image-block','image-url': $(el).attr('src')});
            var img = $('<img>', {src: $(el).attr('src'), 'class': 'add-var-image', 'image-url': $(el).attr('src'), 'style':''});
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

        var d = $('<div>', {'class':'col-xs-3 var-image-block','image-url': el});
        var img = $('<img>', {src: el, 'id':'product-image-'+i, 'class': 'var-image', 'image-url': el, 'image-id':i, 'style':'cursor: default'});
        d.append(img);
        d.append($('<button class="btn btn-danger btn-xs image-delete" style="display:none;position: absolute;cursor: pointer;right: 25px;top: 5px;background-color: rgb(247, 203, 203);color: #B51B18;border-radius: 5px;font-weight: bolder;">x</button>'));

        if (config.photo_editor) {
            d.append($('<button data-toggle="tooltip" data-placement="left" title="Simple Image Editor" class="btn btn-primary btn-xs edit-photo" style="display:none;position: absolute;cursor: pointer;right: 50px;top: 5px;background-color: rgb(226, 255, 228);color: rgb(0, 105, 19);border-radius: 5px;font-weight: bolder;"><i class="fa fa-edit"></i></button>'));
        }

        if (config.advanced_photo_editor) {
            d.append($('<button image-url="'+config.pixlr_image_url+'?image='+el+'" data-toggle="tooltip" data-placement="left" title="Advanced Image Editor" class="btn btn-warning btn-xs advanced-edit-photo" style="display:none;position: absolute;cursor: pointer;right: 80px;top: 5px;background-color: rgb(255, 245, 195);color: rgb(105, 30, 19);border-radius: 5px;font-weight: bolder;"><i class="fa fa-picture-o"></i></button>'));
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
    var imageUrl = encodeURI(window.location.origin+$(this).attr('image-url')),
        image = $(this).siblings('img');
    if (config.advanced_photo_editor) {
        pixlr.settings.exit = window.location.origin+'/pixlr/close';
        pixlr.settings.method = 'POST';
        pixlr.settings.referrer = 'Shopified App';
        // setting to false saves the image but doesn't run the redirect script on pixlr.html
        pixlr.settings.redirect = true;

        pixlr.overlay.show({image: imageUrl, title: image.attr('id'), 
            target: window.location.origin+'/upload/save_image_s3?product='+config.product_id+'&advanced=true&image_id='+image.attr('id')});
    } else {
        swal('Advanced Image Editor', 'Please upgrade your plan to use this feature.', 'warning');
    }
});

$('body').on('click', '#pixlr-background', function(e) {
    e.preventDefault();
    pixlr.overlay.hide();
});

document.renderImages = renderImages;

$(function() {
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

    $('.lazyload').each(function (i, el) {
        if (!$(el).prop('image-loaded')) {
            var cache_name = $(el).attr('store')+'|'+$(el).attr('product')+'|'+$(el).attr('variant');

            if (cache_name in image_cache) {
                $(el).attr('src', image_cache[cache_name]);
                $(el).show('fast');
                return;
            }

            $.ajax({
                url: '/api/product-variant-image',
                type: 'GET',
                data: {
                    store: $(el).attr('store'),
                    product: $(el).attr('product'),
                    variant: $(el).attr('variant'),
                },
                context: {img: $(el), cache_name: cache_name},
                success: function (data) {
                    if (data.status == 'ok') {
                        this.img.attr('src', data.image);
                        this.img.show('fast');

                        image_cache[cache_name] = data.image;
                    }
                },
                error: function (data) {
                },
                complete: function () {
                    this.img.prop('image-loaded', true);
                }
            });
        }
    });
});
})(config, product);
