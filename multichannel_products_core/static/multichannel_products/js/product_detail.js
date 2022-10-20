/* global $, config, toastr, swal, product:true, renderImages, allPossibleCases */
/* global setup_full_editor, cleanImageLink */

(function(config, product) {
'use strict';

var image_cache = {};

var children_count = 0;
var children_deleted = 0;

function showProductInfo(rproduct) {
    product = rproduct;
    if (product) {
        $('#product-title').val(product.title);
        $('#product-price').val(product.price);
        $('#product-type').val(product.product_type);
        $('#product-sku').val(product.sku);
        $('#product-tag').val(product.tags);
        $('#product-vendor').val(product.vendor);
        $('#product-compare-at').val(product.compare_at_price);

        if (product.variants && product.variants.length && !config.connected) {
            $.each(product.variants, function(i, el) {
                var v = $('#variants .variant-simple').clone();
                v.removeClass('variant-simple');
                v.addClass('variant');
                v.find("a.remove-variant").click(removeVariant);
                v.show();

                if (el.title) {
                    v.find('#product-variant-name').val(el.title);
                    v.find('#product-variant-values').val(el.values.join(','));

                    $("#product-variant-values", v).tagit({
                        allowSpaces: true
                    });

                    $('#variants .area').append(v);
                }
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

$('#product-update-btn').click(function (e) {
    e.preventDefault();

    var btn = $(this);
    btn.bootstrapBtn('loading');

    var api_data = {
        'title': $('#product-title').val().trim(),
        'type': $('#product-type').val(),
        'sku': $('#product-sku').val(),
        'tags': $('#product-tag').val(),
        'vendor': $('#product-vendor').val(),
        'published': $('#product-visible').prop('checked'),

        'price': parseFloat($('#product-price').val()),
        'compare_at_price': parseFloat($('#product-compare-at').val()),

        'weight': parseFloat($('#product-weight').val()),
        'weight_unit': $('#product-weight-unit').val(),

        'description': document.editor.getData(),

        'variants': [],
        'images': product.images,

        'available_qty': $('#product-available-qty').val(),
    };

    if (product.variants.length > 0) {
        $('#multichannel-variants tr.multichannel-variant').each(function(j, tr) {

            var variant_data = {
                id: parseInt($(tr).attr('variant-id')),
                image: $(tr).attr('variant-image'),
            };

            var attrs = [
                'price', 'compare_at_price', 'sku'
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
        url: api_url('product-update', 'multichannel'),
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
                if (data.product == config.product_id) {
                    if (data.progress) {
                        btn.text(data.progress);
                        return;
                    }

                    btn.bootstrapBtn('reset');

                    pusher.unsubscribe(config.sub_conf.channel);

                    if (data.success) {
                        toastr.success('Product Updated.','Parent Product Update');
                        setTimeout(function () {
                            window.location.reload(true);
                        }, 1500);
                    }
                    if (data.error) {
                        swal({
                            title: 'Parent Product Update',
                            text: data.error,
                            type: 'error'
                        }, function() {
                            window.location.reload(true);
                        });
                    }
                }
            });
        },
        error: function (data) {
            displayAjaxError('Save Product', data, true);
        }
    });
});

$('#product-save-btn').click(function (e) {
    var btn = $(this);
    productSave(btn, function () {
        toastr.success('Product changes saved!','Product Saved');
    });

});

$('.product-delete-btn').click(function (e) {
    var btn = $(this);
    swal({
            title: "Delete Product",
            text: "This will remove the product and its selected children permanently. " +
                "Are you sure you want to remove this product?",
            type: "warning",
            showCancelButton: true,
            closeOnConfirm: false,
            showLoaderOnConfirm: true,
            confirmButtonColor: "#DD6B55",
            confirmButtonText: "Remove Permanently",
            cancelButtonText: "Cancel"
        },
        function (isConfirmed) {
            if (isConfirmed) {
                productDelete(btn, function (store_type, id, data) {
                    if (['fb', 'ebay', 'google'].includes(store_type)) {
                        var pusher = new Pusher(data.pusher.key);
                        var channel = pusher.subscribe(data.pusher.channel);

                        channel.bind('product-delete', function(eventData) {
                            if (eventData.product === id) {
                                swal.close();
                                pusher.unsubscribe(channel);

                                if (eventData.success) {
                                    children_deleted += 1;
                                    if (children_count === children_deleted) {
                                        toastr.success('Product was deleted!', 'Product Deleted');
                                        swal.close();
                                        window.location.href = window.location.origin + '/multichannel/products?store=p';
                                    }
                                }
                                if (eventData.error) {
                                    displayAjaxError('Delete Product', eventData, true);
                                    // window.location.href = window.location.origin + '/multichannel/products?store=p';
                                }
                            }
                        });
                    } else if (store_type === 'multichannel') {
                        toastr.success('Product was deleted!', 'Product Deleted');
                        swal.close();
                        window.location.href = window.location.origin + '/multichannel/products?store=p';
                    } else {
                        children_deleted += 1;
                        if (children_count === children_deleted) {
                            toastr.success('Product was deleted!', 'Product Deleted');
                            swal.close();
                            window.location.href = window.location.origin + '/multichannel/products?store=p';
                        }
                    }
                });
            }
        });
});

function productDelete(btn, callback) {
    var products = [];
    var platforms = ['shopify', 'woo', 'chq', 'bigcommerce', 'gear', 'gkart', 'ebay', 'fb', 'google'];
    $('.child-stores input[type="checkbox"]:checked').each(function(i, obj) {
        if (platforms.some(function(type) {
            return $(obj).prop('id').includes(type) && $(obj).prop('id') !== type + '-child';
        })) {
            var type = $(obj).prop('id').split('-')[0];
            products.push({
                'id': ['fb', 'ebay', 'google'].includes(type) ? $(obj).attr('data-guid') : $(obj).prop('value'),
                'store_type': type
            });
        }
    });

    $.ajax({
        url: api_url('product', 'multichannel'),
        type: 'DELETE',
        data: JSON.stringify ({
            'product': config.product_id,
            'children': products,
        }),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        context: {btn: btn},
        success: function (data) {
            children_count = products.length;
            if (!children_count && callback) {
                callback('multichannel', product.id, data);
            }
            products.forEach(function(item) {
                var endpoint = item.store_type === 'shopify' ? 'product-delete' : 'product';
                var type = item.store_type === 'shopify' ? 'POST' : 'DELETE';
                $.ajax({
                    url: api_url(endpoint, item.store_type),
                    type: type,
                    data: JSON.stringify({
                        'product': item.id,
                    }),
                    contentType: "application/json; charset=utf-8",
                    dataType: "json",
                    context: {
                        btn: btn
                    },
                    success: function (data) {
                        if (callback) {
                            callback(item.store_type, item.id, data);
                        }
                    },
                    error: function (data) {
                        displayAjaxError('Delete Product', data, true);
                        // window.location.href = window.location.origin + '/multichannel/products?store=p';
                    }
                });
            });
        },
        error: function (data) {
            displayAjaxError('Delete Product', data, true);
        }
    });
}

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
        // 'sku': $('#product-sku').val(),
        'tags': $('#product-tag').val(),
        'vendor': $('#product-vendor').val(),
        // 'weight': parseFloat($('#product-weight').val()),
        // 'weight_unit': $('#product-weight-unit').val(),
        'published': product.published,
        'variants': [],
        'variants_info': product.variants_info,
    };

    if ($('#variants .variant').length) {
        $('#variants .variant').each(function (i, el) {
            api_data.variants.push({
                'title': $(el).find('#product-variant-name').val(),
                'values': $(el).find('#product-variant-values').val().split(',')
            });

        });
    }

    var products = [];
    var platforms = ['shopify', 'woo', 'chq', 'bigcommerce', 'gear', 'gkart', 'ebay', 'fb', 'google'];
    $('.child-stores input[type="checkbox"]:checked').each(function(i, obj) {
        if (platforms.some(function(type) {
            return $(obj).prop('id').includes(type) && $(obj).prop('id') !== type + '-child';
        })) {
            products.push({'id': $(obj).prop('value'), 'type': $(obj).prop('id').split('-')[0]});
        }
    });

    $.ajax({
        url: api_url('parent-product', 'multichannel'),
        type: 'POST',
        data: JSON.stringify ({
            'product': config.product_id,
            'data': JSON.stringify(api_data),
            'children': products,
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
            displayAjaxError('Save Product', data, true);
        },
        complete: function () {
            $(this.btn).bootstrapBtn('reset');
        }
    });
}

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

$('#save-product-notes').click(function (e) {
    var btn = $(this);

    btn.bootstrapBtn('loading');

    $.ajax({
        type: 'POST',
        url: api_url('product-notes', 'multichannel'),
        context: btn,
        data: {
            'notes': $('#product-notes').val(),
            'product': config.product_id,
        },
        success: function(data) {
            if (data.status == 'ok') {
                toastr.success('Modification saved.','Product Notes');
            } else {
                displayAjaxError('Product Notes', data, true);
            }
        },
        error: function(data) {
            displayAjaxError('Product Notes', data, true);
        },
        complete: function() {
            btn.bootstrapBtn('reset');
        }
    });
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
            url: api_url('supplier', 'multichannel'),
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
                displayAjaxError('Product Connections', data, true);
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
            url: api_url('supplier-default', 'multichannel'),
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
                displayAjaxError('Product Connections', data, true);
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
                    url: api_url('supplier', 'multichannel') + '?' + $.param({
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
                        displayAjaxError('Product Connections', data, true);
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
            'image-id': i
        });

        img.on('load', function() {
            if ($(this).attr('src') === $(this).attr('image-url')) {
                return;
            }

            var currentId = $(this).attr('src').match(/\#image_id=(\d+)$/);
            if (!currentId) {
                var imageId = $(this).attr('image-url').match(/\/(\d+)\-large/);
                if (imageId) {
                    imageId = imageId[1];
                    var newUrl = $(this).attr('src') + '#image_id=' + imageId;
                    $(this).attr('src', newUrl);
                    product.images[parseInt($(this).attr('image-id'), 10)] = newUrl;
                }
            }
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
            'href': 'https://app.dropified.com/api/ali/get-image?' + $.param({url: el}),
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
                'html': '<i class="fa fa-edit"></i>'
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
            displayAjaxError('Clipping Magic', data, true);
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
                        multichannel: 1
                    }
                }).done(function(data) {
                    image.attr('src', data.url).siblings(".loader").hide();
                    product.images[parseInt(image.attr('image-id'), 10)] = data.url;
                }).fail(function(data) {
                    displayAjaxError('Clipping Magic', data, true);
                });
            }).fail(function(data) {
                displayAjaxError('Clipping Magic', data, true);
            });
        } else {
            image.siblings(".loader").hide();
            swal('Clipping Magic', response.error.message, 'error');
        }
    });
}

$('.disconnect-child').click(function(e) {
    var product = $(this).attr('data-product-id');
    var storeType = $(this).attr('data-store-type');

    var btn = $(this);
    btn.bootstrapBtn('loading');

    $.ajax({
        url: api_url('disconnect-parent-product', 'multichannel'),
        type: 'POST',
        data: JSON.stringify({
            'product': product,
            'store_type': storeType,
        }),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        context: { btn: btn },
        success: function (data) {
            if (data.status === 'ok') {
                window.location.hash = 'children';
                window.location.reload();
            } else {
                btn.bootstrapBtn('reset');
                displayAjaxError('Child Disconnect', data, true);
            }
        },
        error: function (data) {
            btn.bootstrapBtn('reset');
            displayAjaxError('Child Disconnect', data, true);
        }
    });
});

$('.delete-child').click(function(e) {
    var product = $(this).attr('data-product-id');
    var storeType = $(this).attr('data-store-type');

    var btn = $(this);
    // btn.bootstrapBtn('loading');

    swal({
            title: "Delete Child Product",
            text: "This will remove the product permanently. " +
                "Are you sure you want to remove this product?",
            type: "warning",
            showCancelButton: true,
            closeOnConfirm: false,
            showLoaderOnConfirm: true,
            confirmButtonColor: "#DD6B55",
            confirmButtonText: "Remove Permanently",
            cancelButtonText: "Cancel"
        },
        function (isConfirmed) {
            if (isConfirmed) {
                var endpoint = storeType === 'shopify' ? 'product-delete' : 'product';
                var type = storeType === 'shopify' ? 'POST' : 'DELETE';
                $.ajax({
                    url: api_url(endpoint, storeType),
                    type: type,
                    data: JSON.stringify({
                        'product': product,
                    }),
                    contentType: "application/json; charset=utf-8",
                    dataType: "json",
                    context: {btn: btn},
                    success: function (data) {
                        if (data.status === 'ok') {
                            if (['fb', 'ebay', 'google'].includes(storeType)) {
                                var pusher = new Pusher(data.pusher.key);
                                var channel = pusher.subscribe(data.pusher.channel);

                                channel.bind('product-delete', function (eventData) {
                                    if (eventData.product === product) {
                                        swal.close();
                                        pusher.unsubscribe(channel);

                                        if (eventData.success) {
                                            window.location.hash = 'children';
                                            window.location.reload();
                                            toastr.success('Child Product was deleted!', 'Product Deleted');
                                            swal.close();
                                        }
                                        if (eventData.error) {
                                            displayAjaxError('Child Delete', eventData, true);
                                        }
                                    }
                                });
                            } else {
                                window.location.hash = 'children';
                                window.location.reload();
                                toastr.success('Child Product was deleted!', 'Product Deleted');
                                swal.close();
                            }
                        } else {
                            displayAjaxError('Child Delete', data, true);
                        }
                    },
                    error: function (data) {
                        displayAjaxError('Child Delete', data, true);
                    }
                });
            }
        }
    );
});

function handleEbayErrorsList(parsed_ebay_errors_list) {
    var html_ebay_errors_list = '<div class="panel-group text-left" id="accordion" role="tablist" aria-multiselectable="true">';

    parsed_ebay_errors_list.forEach(
        function(ebay_error, index) {
            html_ebay_errors_list += '<div class="panel panel-default">';
            html_ebay_errors_list += '<div class="panel-heading" role="tab" id="heading' + index + '">';
            html_ebay_errors_list += '<h4 class="panel-title">';
            html_ebay_errors_list += '<a role="button" data-toggle="collapse" data-parent="#accordion"';
            html_ebay_errors_list += 'href="#collapse' + index + '" aria-expanded="false" aria-controls="collapse' + index +'">';
            html_ebay_errors_list += 'Error Code ' + ebay_error.error_code + ': </br>' + ebay_error.short_message + '</a></h4></div>';
            html_ebay_errors_list += '<div id="collapse' + index + '" class="panel-collapse collapse" role="tabpanel" aria-labelledby="heading' + index + '">';
            html_ebay_errors_list += '<div class="panel-body">' + ebay_error.long_message + '</div></div></div>';
        }
    );
    html_ebay_errors_list += '</div>';

    return html_ebay_errors_list;
}

$('.unpublish-child').click(function (e) {
    var product = $(this).attr('data-product-id');
    var storeType = $(this).attr('data-store-type');

    e.preventDefault();

    swal({
        title: "Unpublish Product",
        text: "Are you sure you want to unpublish this product?",
        type: "warning",
        showCancelButton: true,
        closeOnCancel: true,
        closeOnConfirm: false,
        showLoaderOnConfirm: true,
        confirmButtonColor: "#DD6B55",
        confirmButtonText: "Unpublish",
        cancelButtonText: "Cancel"
    },
    function(isConfirmed) {
        if (isConfirmed) {
            $.ajax({
                url: api_url('product-connect', storeType) + '?' + $.param({
                    product: product,
                }),
                type: 'DELETE',
                success: function (data) {
                    window.location.hash = 'children';
                    window.location.reload();
                },
                error: function (data) {
                    displayAjaxError('Unpublish Product', data, true);
                }
            });
        }
    });
});

$('.publish-child').click(function (e) {
    var product = $(this).attr('data-product-id');
    var storeType = $(this).attr('data-store-type');

    var btn = $(this);
    btn.bootstrapBtn('loading');

    $.ajax({
        url: api_url('export-child-product', 'multichannel'),
        type: 'POST',
        data: JSON.stringify({
            'product': product,
            'store_type': storeType,
        }),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        context: {btn: btn},
        success: function (data) {
            if ('product' in data) {
                if (storeType === 'shopify') {
                    window.location.hash = 'children';
                    window.location.reload();
                }

                var channel_event = 'product-export';
                if (storeType === 'fb') {
                    channel_event = 'fb-product-export';
                } else if (storeType === 'google') {
                    channel_event = 'google-product-export';
                }

                var pusher = new Pusher(data.product.pusher.key);
                var channel = pusher.subscribe(data.product.pusher.channel);

                channel.bind(channel_event, function (data) {
                    if (data.progress) {
                        return;
                    }
                    pusher.unsubscribe(channel);
                    if (data.success) {
                        if (['fb', 'ebay', 'google'].includes(storeType)) {
                            setTimeout(function () {
                                window.location.hash = 'children';
                                window.location.reload();
                            }, 300);
                        } else {
                            window.location.hash = 'children';
                            window.location.reload();
                        }
                    } else {
                        btn.bootstrapBtn('reset');
                        if (['fb', 'ebay', 'google'].includes(storeType) && data.product_url) {
                            window.open(window.location.origin + data.product_url, '_blank');
                        }
                        if (storeType === 'ebay' && data.parsed_ebay_errors_list) {
                            data = handleEbayErrorsList(data.parsed_ebay_errors_list);
                        }
                        displayAjaxError('Export To Store', data, true);
                    }
                });
            } else {
                btn.bootstrapBtn('reset');
                displayAjaxError('Export To Store', data, true);
            }
        },
        error: function (data) {
            btn.bootstrapBtn('reset');
            displayAjaxError('Export To Store', data, true);
        }
    });
});

(function() {
    setup_full_editor('product-description');

    showProductInfo(product);

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
    }, 200);

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

    $('.child-stores input[type="checkbox"]').on('ifChecked', function(event){
        var platforms = ['shopify', 'woo', 'chq', 'bigcommerce', 'gear', 'gkart', 'ebay', 'fb', 'google'];
        if ($(this).attr('value') === 'all') {
            $('.child-stores input[type="checkbox"]').each(function(i, obj) {
                $(obj).iCheck('check');
            });
        } else if (platforms.includes($(this).attr('value'))) {
            var value = $(this).attr('value');
            $('.child-stores input[type="checkbox"]').each(function(i, obj) {
                if ($(obj).attr('id').startsWith(value)) {
                    $(obj).iCheck('check');
                }
            });
        } else {
            var type = $(this).attr('id').split('-')[0];
            var checkedType = 0;
            var uncheckedType = 0;
            $('.child-stores input[type="checkbox"]').each(function(i, obj) {
                if ($(obj).attr('id').startsWith(type)) {
                    if ($(obj).prop('checked')) {
                        checkedType += 1;
                    } else {
                        uncheckedType += 1;
                    }
                }
            });
            if (uncheckedType === 1 && checkedType > 0) {
                $('.child-stores input[value="' + type +'"]').iCheck('check');
            }
        }
        // check "All" if all selected
        if ($('.child-stores input[type="checkbox"]:checked').length ===
            $('.child-stores input[type="checkbox"]').length - 1 &&
            !$('.child-stores #all-child').prop('checked')
        ) {
            $('.child-stores #all-child').iCheck('check');
        }
    });

    $('.child-stores input[type="checkbox"]').on('ifUnchecked', function(event){
        var platforms = ['shopify', 'woo', 'chq', 'bigcommerce', 'gear', 'gkart', 'ebay', 'fb', 'google'];
        if ($(this).attr('value') === 'all') {
            $('.child-stores input[type="checkbox"]').each(function(i, obj) {
                $(obj).iCheck('uncheck');
            });
        } else if (platforms.includes($(this).attr('value'))) {
            var value = $(this).attr('value');
            $('.child-stores input[type="checkbox"]').each(function(i, obj) {
                if ($(obj).attr('id').startsWith(value)) {
                    $(obj).iCheck('uncheck');
                }
            });
            $('.child-stores #all-child').prop('checked', false).iCheck('update');
        } else {
            var type = $(this).attr('id').split('-')[0];
            $('.child-stores input[value="' + type +'"]').prop('checked', false).iCheck('update');
            $('.child-stores #all-child').prop('checked', false).iCheck('update');
        }
    });

    $('tr.parent-variant input').change(function(e) {
        var title = $(this).closest('.parent-variant').attr('variant-title');
        if ($(this).prop('name') === 'price') {
            Object.assign(product.variants_info[title], {'price': $(this).prop('value')});
        } else if ($(this).prop('name') === 'compare_at_price') {
            Object.assign(product.variants_info[title],
                {'compare_at': $(this).prop('value'), 'compare_at_price': $(this).prop('value')});
        }
    });

    $('.child-stores #all-child').iCheck('check');

    $('.connect-to-store').click(function (e) {
        var storeId = $(this).attr('data-store-id');
        var storeType = $(this).attr('data-store-type');

        var btn = $(this);
        btn.bootstrapBtn('loading');

        $.ajax({
            url: api_url('child-product', 'multichannel'),
            type: 'POST',
            data: JSON.stringify({
                'parent_product': product.id,
                'store': {
                    'id': storeId,
                    'type': storeType,
                },
                'publish': false,
                'override_fields': {
                    'weight': $('#product-weight').val() ? parseFloat($('#product-weight').val()) : 0,
                    'weight_unit': $('#product-weight-unit').val(),
                },
            }),
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            context: {btn: btn},
            success: function (data) {
                if ('product' in data) {
                    if (['fb', 'ebay', 'google'].includes(storeType)) {
                        var channel_event = 'product-save';
                        if (storeType === 'ebay') {
                            channel_event = 'ebay-product-save';
                        } else if (storeType === 'fb'){
                            channel_event = 'fb-product-save';
                        } else if (storeType === 'google'){
                            channel_event = 'google-product-save';
                        }
                        var pusher = new Pusher(data.product.pusher.key);
                        var channel = pusher.subscribe(data.product.pusher.channel);

                        channel.bind(channel_event, function (data) {
                            pusher.unsubscribe(channel);
                            if (data.success) {
                                window.location.hash = 'children';
                                window.location.reload();
                            } else {
                                displayAjaxError('Connect To Store', data, true);
                            }
                        });
                    } else {
                        window.location.hash = 'children';
                        window.location.reload();
                    }
                } else {
                    displayAjaxError('Connect To Store', data, true);
                }
            },
            error: function (data) {
                btn.bootstrapBtn('reset');
                displayAjaxError('Connect To Store', data, true);
            }
        });
    });
})();
})(config, product);
