/* global $, config, toastr, swal, product:true, renderImages, allPossibleCases */
/* global setup_full_editor, cleanImageLink */

(function(config, product) {
'use strict';

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

        var has_advanced_variants = false;
        if(product.hasOwnProperty('advanced_variants_data')) {
            has_advanced_variants = true;
        }

        if(has_advanced_variants && product.advanced_variants_data.length) {
            product.advanced_variants_data.forEach(function(data, i) {
            var vdata = { // jshint ignore:line
                "title": data.title,
                "price": data.price,
                "compare_at_price": data.compare_at_price,
                "sku": data.sku,
                "image_src": data.image,
                "weight": data.weight,
                "weight_unit": data.weight_unit,
                "option1": data.option1,
                "option2": data.option2,
                "option3": data.option3,
            };
            $('#product-variants tbody').append(drawSeparatedVariant(vdata, i));
        });
        }
        else {
            var variant_object_keys = [];
            var variant_info = '';
            if(product.hasOwnProperty('variants_info')) {
                variant_info = product.variants_info;
                if(typeof variant_info === 'object') {
                    variant_object_keys = Object.keys(variant_info);
                }
            }
            var vars_list = [];
            $('#variants .variant').each(function (i, el) {
                var vals = $(el).find('#product-variant-values').val().split(',');
                vars_list.push(vals);
            });
            if (vars_list.length > 0) {
                vars_list = allPossibleCases(vars_list);
                for (var i = 0; i < vars_list.length; i++) { // jshint ignore:line
                    var title = vars_list[i].join ? vars_list[i].join(' / ') : vars_list[i];

                    var vprice = product.price;
                    var compare_at_price = '';
                    var image_src = '';
                    if ($('#product-compare-at').val().length) {
                        compare_at_price = parseFloat($('#product-compare-at').val());
                    }

                    if(variant_object_keys.length) {
                        if(variant_object_keys.includes(title)) {
                            vprice = variant_info[title].price;
                            if ($('#product-compare-at').val().length) {
                                compare_at_price = variant_info[title].compare_at;
                            }
                            image_src = variant_info[title].image;
                        }
                    }

                    var vdata = { // jshint ignore:line
                        "price": vprice,
                        "title": title,
                        "compare_at_price": compare_at_price,
                        "image_src": image_src,
                        "weight": parseFloat($('#product-weight').val()),
                        "weight_unit": product.weight_unit,
                        "sku": '',
                    };
                    if (typeof(vars_list[i]) == "string") {
                        vdata["option1"] = vars_list[i];
                        if (product.variants_sku && product.variants_sku.hasOwnProperty(vars_list[i])) {
                            vdata["sku"] = product.variants_sku[vars_list[i]];
                        }
                    } else {
                        var sku = [];

                        $.each(vars_list[i], function (j, va) { // jshint ignore:line
                            vdata["option"+(j+1)] = va;
                            if (product.variants_sku && product.variants_sku.hasOwnProperty(va)) {
                                sku.push(product.variants_sku[va]);
                            }
                        });

                        if (sku.length) {
                            vdata["sku"] = sku.join(';');
                        }
                    }

                    if ($('#product-weight').val().length) {
                        vdata.weight = parseFloat($('#product-weight').val());
                        vdata.weight_unit = $('#product-weight-unit').val();
                    }

                    if (vdata.title in config.shopify_variants) {
                        vdata.id = config.shopify_variants[vdata.title];
                    }

                    $('#product-variants tbody').append(drawSeparatedVariant(vdata, i));
                }
            }
        }
        renderImages();
    }
}

function drawSeparatedVariant(vdata, i) {
    var var_str = '<tr class="shopify-variant">' + '<td><image src="' + vdata.image_src + '" class="unveil" style="width:64px"></td>' +
            '<td><input type="hidden" name="option1" value="' + vdata.option1 + '">' +
            '<input type="hidden" name="option2" value="' + vdata.option2 + '">' +
            '<input type="hidden" name="option3" value="' + vdata.option3 + '">' +
            '<input type="hidden" name="title" value="' + vdata.title + '">' + vdata.title + '</td>' +
            '<input type="hidden" name="image" value="' + vdata.image_src + '">' +

            '<td style="white-space:nowrap"><div class="input-group" style="width:120px"><span class="input-group-addon popup-currency-sign">$</span><input type="number" name="price" class="form-control splitted-price" value="' +
            vdata.price + '" data-price="' + vdata.price + '"/></div></td>' +

            '<td style="white-space:nowrap"><div class="input-group" style="width:120px"><span class="input-group-addon popup-currency-sign">$</span><input type="number" class="form-control splitted-compare-at" name="compare_at_price" ' + ' value="' +
            vdata.compare_at_price + '"data-price="' + vdata.compare_at_price + '"/></div></td>' +

            '<td style="white-space:nowrap"><div class="input-group" style="width:120px"><input type="text" name="sku" class="form-control splitted-price" value="' +
            vdata.sku + '" data-price="' + vdata.sku + '"/></div></td>' +
            '<td style="white-space:nowrap"><input class="form-control" type="number" name="weight" value="' + vdata.weight +'" min="0" step="0.1" data-number-to-fixed="2" data-number-stepfactor="100" style="display:inline-block;width:100px;"><select class="form-control" name="weight_unit" style="width:65px;display:inline-block;">';

            var weight_unit_array = ['g', 'kg', 'oz', 'lb'];
            var weight_unit_str = '';
            for(var unit in weight_unit_array) {
                if(vdata.weight_unit === weight_unit_array[unit]) {
                weight_unit_str+= '<option selected="selected" value="' + vdata.weight_unit +'">' + vdata.weight_unit + '</option>';
                } else {
                    weight_unit_str+= '<option value="' + weight_unit_array[unit]+ '">' + weight_unit_array[unit] + '</option>';
                }
            }
            var_str = var_str + weight_unit_str + '</select></td>' + '</tr>';

            return var_str;
}

var elems = Array.prototype.slice.call(document.querySelectorAll('.js-switch'));
elems.forEach(function(html) {
    var switchery = new Switchery(html, {
        color: '#93c47d',
        size: 'small'
    });
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

            if(!$('#toast-container').prop('notified')) {
                toastr.success('Product Exported.','Shopify Export');
            }

        } else {
            if(!$('#toast-container').prop('notified')) {
                toastr.success('Product Updated in Shopify.','Shopify Update');
            }

            window.location.href = window.location.href;
        }

        $('#toast-container').prop('notified', true);
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
                if (!$('#advanced_variants').prop('checked')) {
                    vars_list = allPossibleCases(vars_list);
                    for (var i = 0; i < vars_list.length; i++) { // jshint ignore:line
                        var title = vars_list[i].join ? vars_list[i].join(' & ') : vars_list[i];

                        var vdata = { // jshint ignore:line
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

                            $.each(vars_list[i], function (j, va) { // jshint ignore:line
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
                    var element = $('#product-variants tr.shopify-variant');
                    element.each(function(k, tr) {
                        var variant_data = {};
                        var attrs = [
                            'option1', 'option2', 'option3', 'title', 'weight_unit',
                            'price', 'compare_at_price', 'weight', 'sku'
                        ];
                        $.each(attrs, function(k, att) {
                            var att_val = $('[name="' + att + '"]', tr).val();
                            if (att_val && att_val.length > 0 && att_val != "undefined") {
                                if (k === 'price' || k === 'compare_at_price' || k === 'weight') {
                                    att_val = parseFloat(att_val);
                                }
                                if (att === 'title') {
                                    att_val = att_val.replace('/', '&');
                                }
                                variant_data[att] = att_val;
                            } else {
                                variant_data[att] = '';
                            }
                        });
                        api_data.product.variants.push(variant_data);
                    });
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
                'price', 'compare_at_price', 'weight', 'sku'
            ];

            $.each(attrs, function(k, att) {
                var att_val = $('[name="' + att + '"]', tr).val();
                if (att_val && att_val.length > 0) {
                    if (k === 'price' || k === 'compare_at_price' || k === 'weight') {
                        att_val = parseFloat(att_val);
                    }

                    variant_data[att] = att_val;
                } else {
                    variant_data[att] = '';
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
            'old_to_new_url': JSON.stringify(config.old_to_new_url),
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
    var targetVariants = [];

    if (config.shopify_options === null) {
        targetVariants = product.variants.filter(function(v) { return v.title === val; });
        if (targetVariants.length > 0) {
            $('#split-variants-count').text(targetVariants[0].values.length);
            $('#split-variants-values').text(targetVariants[0].values.join(', '));
        }
    } else {
        targetVariants = config.shopify_options.filter(function(o) { return o.name === val; });
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
                  toastr.success('The variants are now split into new products.\r\nThe new products will get connected to shopify very soon.', 'Product Split!');
                } else {
                  toastr.success('The variants are now split into new products.', 'Product Split!');
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
        'boards': $('#boards').val(),
        'variants': [],
        'advanced_variants_data': []
    };

    if ($('#variants .variant').length) {
        $('#variants .variant').each(function (i, el) {
            api_data.variants.push({
                'title': $(el).find('#product-variant-name').val(),
                'values': $(el).find('#product-variant-values').val().split(',')
            });

        });
    }

    $('#product-variants tr.shopify-variant').each(function(j, tr) {
        var attrs = [
            'option1', 'option2', 'option3', 'title', 'weight_unit',
            'price', 'compare_at_price', 'weight', 'sku', 'image'
        ];
        var variant_data = {};

        $.each(attrs, function(k, att) {
            var att_val = $('[name="' + att + '"]', tr).val();
            if (att_val && att_val.length > 0) {
                if (k === 'price' || k === 'compare_at_price' || k === 'weight') {
                    att_val = parseFloat(att_val);
                }

                variant_data[att] = att_val;
            } else {
                variant_data[att] = '';
            }
        });
        api_data.advanced_variants_data.push(variant_data);
    });

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

$('#randomize-images-btn').click(function (e) {
    e.preventDefault();

    var product_id = $(this).attr('product-id');

    $(this).bootstrapBtn('loading');

    PusherSubscription.productRandomizeImageNames();

    $.ajax({
        url: '/api/product-randomize-image-names',
        type: 'POST',
        data: {
            product: product_id
        },
        context: {btn: $(this)},
        success: function (data) {
            $('#modal-shopify-image-randomize .progress-bar-success').css('width', '0%');
            $('#modal-shopify-image-randomize .progress-bar-danger').css('width', '0%');
            $('#modal-shopify-image-randomize').modal({ backdrop: 'static', keyboard: false });
        },
        error: function (data) {
            this.btn.bootstrapBtn('reset');
            displayAjaxError('Randomizing Images URLs', data);
        }
    });
});

function matchImagesWithExtra(parent) {
    if (typeof parent === "undefined") {
        parent = "modal-add-image";
    }

    $('#' + parent + ' .extra-added').remove();
    $('#' + parent + ' .add-var-image-block').each(function(i, el) {
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

    for (var i = 0; i < product.images.length; i++) {
        if (i != imageID) {
            new_images.push(product.images[i]);
        }
    }

    product.images = new_images;
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

    $('.sync-inventory-btn', target).click(function(e) {
        e.preventDefault();

        var btn = $(this);
        var form = $(this).parents('.product-export-form');

        btn.bootstrapBtn('loading');

        $.ajax({
            type: 'POST',
            url: api_url('sync_with_supplier', 'shopify'),
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
            url: '/api/product-metadata',
            context: btn,
            data: {
                'original-link': $('.product-original-link', form).val(),
                'shopify-link': $('.product-shopify-link', form).val(),
                'supplier-name': $('.product-supplier-name', form).val(),
                'supplier-link': $('.product-supplier-link', form).val(),
                'supplier-notes': $('.product-supplier-notes', form).val(),
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
    }

    return -1;
}

function reorderImages() {
    $('#var-images .var-image-block').each(function(i, el) {
        product.images[i] = $(el).attr('image-url');
    });
    renderImages();
}

dragula([document.getElementById('var-images')], {
        moves: function(el, container, handle) {
            return (/image\-move/).test(handle.className) || (/order\-handle/).test(handle.className);
        }
    }).on('grag', function(el) {
    }).on('drop', function(el) {
        if (config.shopify_images) {
            var f_img_id = $(el).find('img').attr('image-id');
            var data = {
                'store': $('#var-images').data('store'),
                'product': $('#var-images').data('productid'),
                'image_id': config['shopify_images'][parseInt(f_img_id)]['id'],
                'position':  $(el).index() + 1
            };

            $.ajax({
                url: api_url('image-position', 'shopify'),
                type: 'POST',
                data: data,
                dataType: 'json',
                success: function(data) {
                    reorderImages();
                },
                error: function(data) {
                    renderImages();
                },
            });
        } else {
            reorderImages();
        }
    }).on('over', function(el, container) {
        $(el).css('cursor', 'move');
    }).on('out', function(el, container) {
        $(el).css('cursor', 'inherit');
    });

function renderImages() {
    $('#var-images').empty();

    $.each(product.images, function (i, el) {

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

        buttons.push($('<button>', {
            'title': "Move",
            'class': "btn btn-default btn-xs itooltip image-move",
            'html': '<i class="fa fa-bars order-handle"></i>'
        }));

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

    $('#var-images .var-image-block img').click(function (e) {
        e.preventDefault();

        var imgs = [];
        var idx = 0;

        $('#var-images .var-image-block img').each(function (i, el) {
            imgs.push({
                href: $(el).prop('src'),
            });

            if (el == e.target) {
                idx = i;
            }
        });

        blueimp.Gallery(imgs, {index: idx});
    });
}

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
                    $('#modal-add-image #images-row').append($('<img>', {'src': el}));
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

$('.remove-background-image-editor').click(function(e) {
    e.preventDefault();

    initClippingMagic($(this));
});

function showExcludeProgress(is_exclude) {
    var pusher = new Pusher(config.sub_conf.key);
    var channel = pusher.subscribe(config.sub_conf.channel);
    var el = $('#modal-exclude-progress .progress-bar-success');

    channel.bind('product-exclude', function(data) {
        if (data.product == config.product_id) {
            el.css('width', ((data.progress * 100.0) / data.total) + '%');

            if (data.progress == data.total) {
                if (is_exclude) {
                    toastr.success('Product is excluded', 'Exclude Product');
                } else {
                    toastr.success('Product is included', 'Include Product');
                }

                $('#modal-exclude-progress').modal('hide');

                setTimeout(function () {
                    window.location.hash = '#connections';
                    window.location.reload();
                }, 1000);
            }
        }
    });

    $('#modal-exclude-progress').modal({
        backdrop: 'static',
        keyboard: false
    });

    el.css('width', '0');
    swal.close();
}

$('#exclude-product').on('click', function(e) {
    e.preventDefault();

    swal({
        title: 'Exclude Product',
        text: 'Are you sure you want to exclude this product?',
        type: "warning",
        animation: false,
        showCancelButton: true,
        closeOnCancel: true,
        closeOnConfirm: false,
        confirmButtonText: "Yes",
        cancelButtonText: "Cancel"
    },
    function(isConfirmed) {
        if (isConfirmed) {
            $.ajax({
                url: api_url('product-exclude'),
                type: 'POST',
                data: {
                    product: config.product_id,
                },
            }).done(function(data) {
                showExcludeProgress(true);

                $('.include-product-div').show().addClass('m-t').addClass('m-b');
                $('.include-product-div').html('');
            }).fail(function(data) {
                displayAjaxError('Exclude Product', data);
            });
        }
    });
});

$('#include-product').on('click', function(e) {
    e.preventDefault();

    swal({
        title: 'Include Product',
        text: 'Are you sure you want to include this product?',
        type: "warning",
        animation: false,
        showCancelButton: true,
        closeOnCancel: true,
        closeOnConfirm: false,
        confirmButtonText: "Yes",
        cancelButtonText: "Cancel"
    },
    function(isConfirmed) {
        if (isConfirmed) {
            $.ajax({
                url: api_url('product-include'),
                type: 'POST',
                data: {
                    product: config.product_id,
                },
            }).done(function(data) {
                showExcludeProgress(false);

                $('.exclude-product-div').show().addClass('m-t').addClass('m-b');
                $('.include-product-div').html('');
            }).fail(function(data) {
                displayAjaxError('Include Product', data);
            });
        }
    });
});

$('#advanced_variants').on('change', function(){
    if($(this).prop('checked')) {
        $('#variants').hide();
        $('#product-variants').show();
    } else {
        $('#variants').show();
        $('#product-variants').hide();
    }
});

$('.delete-product-btn').click(function(e) {
    e.preventDefault();

    var btn = $(this);
    var product = btn.attr('product-id');

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
                $.ajax({
                    url: '/api/product-delete',
                    type: 'POST',
                    data: {
                        product: product,
                    },
                    success: function(data) {
                        swal.close();
                        toastr.success("The product has been deleted.", "Deleted!");

                        setTimeout(function() {
                            window.location.href = '/product';
                        }, 1000);
                    },
                    error: function(data) {
                        displayAjaxError('Delete Product', data);
                    }
                });
            }
        });
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
                        clippingmagic: true,
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

$('.parent-product-disconnect').click(function(e) {
    var btn = $(this);
    btn.bootstrapBtn('loading');

    $.ajax({
        url: api_url('disconnect-parent-product', 'multichannel'),
        type: 'POST',
        data: JSON.stringify({
            'product': config.product_id,
            'store_type': 'shopify',
        }),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        context: { btn: btn },
        success: function (data) {
            if (data.status === 'ok') {
                window.location.hash = 'connections';
                window.location.reload();
            } else {
                btn.bootstrapBtn('reset');
                displayAjaxError('Parent Disconnect', data);
            }
        },
        error: function (data) {
            btn.bootstrapBtn('reset');
            displayAjaxError('Parent Disconnect', data);
        }
    });
});

$('.parent-product-create').click(function(e) {
    var btn = $(this);
    btn.bootstrapBtn('loading');

    $.ajax({
        url: api_url('parent-product', 'multichannel'),
        type: 'POST',
        data: JSON.stringify({
            'product_id': config.product_id,
            'store_type': 'shopify',
        }),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        context: { btn: btn },
        success: function (data) {
            if (data.status === 'ok') {
                if (data.product) {
                    window.location = data.product.url + '#children';
                } else {
                    window.location.hash = 'connections';
                    window.location.reload();
                }
            } else {
                btn.bootstrapBtn('reset');
                displayAjaxError('Parent Create', data);
            }
        },
        error: function (data) {
            btn.bootstrapBtn('reset');
            displayAjaxError('Parent Create', data);
        }
    });
});

$('.parent-product-link').click(function(e) {
    e.preventDefault();

    $('#modal-multichannel-product').modal('show');
});

window.multichannelProductSelected = function (master_id) {
    $('#modal-multichannel-product').modal('hide');
    $('.parent-product-link').bootstrapBtn('loading');

    $.ajax({
        url: api_url('link-product', 'multichannel'),
        type: 'POST',
        data: {
            master_id: master_id,
            product: config.product_id,
            store_type: 'shopify',
        },
        success: function (data) {
            if ('product' in data) {
                window.location.hash = 'connections';
                window.location.reload();
            } else {
                $('.parent-product-link').bootstrapBtn('reset');
                displayAjaxError('Link Product', data, true);
            }
        },
        error: function (data) {
            $('.parent-product-link').bootstrapBtn('reset');
            displayAjaxError('Link Product', data, true);
        }
    });
};

var PusherSubscription = {
    init: function() {
        if (!window.pusher || !window.channel) {
            window.pusher = new Pusher(config.sub_conf.key);
            window.channel = window.pusher.subscribe(config.sub_conf.channel);
        }
    },
    productRandomizeImageNames: function() {
        this.init();

        window.channel.bind('product-randomize-image-names', function(data) {
            if (data.product == config.product_id) {
                if (data.success + data.fail >= data.total) {
                    // Completed
                    $('#randomize-images-btn').bootstrapBtn('reset');
                    $('#modal-shopify-image-randomize').modal('hide');
                    toastr.success('Done','Randomizing Images URLs');
                }
                if (data.total > 0) {
                    $('#modal-shopify-image-randomize .progress-bar-success').css('width', ((data.success * 100.0) / data.total) + '%');
                    $('#modal-shopify-image-randomize .progress-bar-danger').css('width', ((data.fail * 100.0) / data.total) + '%');
                }
                if (data.error) {
                    $('#modal-shopify-image-randomize .error').html(data.error);
                }
                if (data.image) {
                    // Update image variables with new image url
                    var old_src;
                    $.each(config.shopify_images, function (i, img) {
                        if (img.id == data.image.old_id) {
                            old_src = img.src;
                            config.shopify_images[i] = data.image.image;
                        }
                    });
                    $.each(product.images, function (i, src) {
                        if (src == old_src) {
                            product.images[i] = data.image.image.src;
                        }
                    });
                    if (data.variants_images) {
                        product.variants_images = data.variants_images;
                    }
                }
            }
        });
    },
};

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
                'Pusher service is not loaded', {timeOut: 0});
            return;
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

    $('#modal-upload-image a[data-toggle="tab"]').on('shown.bs.tab', function(e) {
        if ($(e.target).attr('href') == '#upload-tab2') {
            var par = $('#upload-tab2');

            if (!$('#loader', par).hasClass('hide') && !$('#loader .sk-spinner', par).hasClass('hide')) {
                $.post('/api/youzign-images')
                    .done(function(data) {
                        $.each(data.data, function(i, image) {
                            if (i % 4 === 0) {
                                $('<div>', {
                                    'class': 'col-xs-12',
                                }).appendTo($('#images', par));
                            }

                            $('<div>', {
                                'class': 'col-xs-3 add-var-image-block',
                                'html': '<img src="//cdn.dropified.com/static/img/blank.gif" data-src="' + image.image_src[0] + '" class="add-var-image unveil" />'
                            }).appendTo($('#images', par));
                        });

                        $('#loader', par).addClass('hide');
                        $('#images', par).removeClass('hide');
                        $('.unveil', par).unveil();

                        matchImagesWithExtra("modal-upload-image");
                    })
                    .fail(function(data) {
                        $('#loader .sk-spinner', par).addClass('hide');
                        displayAjaxError('YouZign', data);
                    });
            }
        }
    });

    $('select#boards').select2({
        language: {
            noResults: function() {
                return "Add New";
            }
        },
        escapeMarkup: function(markup) {
            return markup;
        }
    });

    $(document).on('click', '.select2-results__option.select2-results__message', function() {
        $('#modal-board-add [name="title"]').val($('.select2-search__field').val());
        $('#modal-board-add').modal('show');
    });

    window.onBoardAdd = function(board) {
        $('<option>', {
            value: board.id,
            html: board.title,
            text: board.title,
            selected: true
        }).appendTo($('select#boards'));

        $('select#boards').trigger('change.select2');
    };

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
})();
})(config, product);
