/* global $, config, toastr, swal, product:true, renderImages, allPossibleCases */
/* global setup_full_editor, cleanImageLink */

(function(config, product) {
'use strict';

var image_cache = {};

/* jshint ignore:start */
function uuidv4() {
    return ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, function (c) {
            return (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16);
        }
    );
}
/* jshint ignore:end */

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
        else if (product.options && product.options.length) {
            $.each(product.options, function (i, el) {
                var v = $('#variants .variant-simple').clone();
                v.removeClass('variant-simple');
                v.addClass('variant');
                v.find("a.remove-variant").click(removeVariant);
                v.show();

                v.find('#product-variant-name').val(el.title).prop('disabled', true);
                v.find('#product-variant-values').val(el.values.join(',')).prop('disabled', true);

                v.data('changes-look', el.changes_look);
                v.data('thumbnails', el.thumbnails);

                $("#product-variant-values", v).tagit({
                    allowSpaces: true,
                    // readOnly: true,
                    beforeTagAdded: function (event, ui) {
                        if (!ui.duringInitialization) {
                            beforeTagAdded(event, ui);
                        }
                    },
                    afterTagRemoved: function (event, ui) {
                        if (!ui.duringInitialization) {
                            afterTagRemoved(event, ui);
                        }
                    }
                });

                $('#variants .area').append(v);
            });
            $('#variants .area').next().remove();
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
    v.data('changes-look', false);
    v.data('thumbnails', []);

    $("#product-variant-values", v).tagit({
        allowSpaces: true,
        beforeTagAdded: function (event, ui) {
            beforeTagAdded(event, ui);
        },
        afterTagRemoved: function (event, ui) {
            afterTagRemoved(event, ui);
        }
    });

    $('#variants .area').append(v);
});

function afterTagRemoved(event, ui) {
    var updatedVariants = [];
    product.variants.forEach(function (item) {
        item.variant = item.variant.filter(function (variant) {
            if (variant !== ui.tagLabel) {
                return variant;
            } else {
                updatedVariants.push(item.id);
            }
        });
    });
    if (updatedVariants && $(event.target).tagit("assignedTags").length !== 0) {
        product.variants.forEach(function (item) {
            if (updatedVariants.includes(item.id)) {
                item.variant.push($(event.target).tagit("assignedTags")[0]);
            }
        });
        $('#commercehq-variants tr.commercehq-variant').each(function (j, tr) {
            var id = +$(tr).attr('variant-id');
            if (isNaN(id)) {
                id = $(tr).attr('variant-id');
            }
            if (updatedVariants.includes(id)) {
                $('span[data-name="title"]', tr).text($('span[data-name="title"]', tr).text().replace(ui.tagLabel, $(event.target).tagit("assignedTags")[0]).replace(/\s\/\s$/, '').replace(/^\s\/\s/, ''));
            }
        });
    } else if ($(event.target).tagit("assignedTags").length === 0) {
        $('#commercehq-variants tr.commercehq-variant').each(function (j, tr) {
            var id = +$(tr).attr('variant-id');
            if (isNaN(id)) {
                id = $(tr).attr('variant-id');
            }
            if (updatedVariants.includes(id)) {
                $('span[data-name="title"]', tr).text($('span[data-name="title"]', tr).text().replace(ui.tagLabel, '').replace(/\s\/\s$/, '').replace(/^\s\/\s/, ''));
            }
        });
    }
}

function beforeTagAdded(event, ui) {
    if ($(event.target).tagit("assignedTags").length === 0) {
        product.variants.forEach(function (item) {
            item.variant.push(ui.tagLabel);
        });
        $('#commercehq-variants tr.commercehq-variant').each(function (j, tr) {
            $('span[data-name="title"]', tr).text($('span[data-name="title"]', tr).text() + ' / ' + ui.tagLabel);
        });
    }
}

$("a.edit-variant-options").click(function (e) {
    e.preventDefault();

    if (!$('#variants').is(':hidden')) {
        $(this).text('Edit Variant Options');
    } else {
        $(this).text('Hide Variant Options');
    }

    $('#variants').toggle();
});

$('#modal-add-variant-options .save-add-options').click(function (e) {
    var options = $('#modal-add-variant-options #product-variant-options').val();
    if (options) {
        product.options = options.split(',').map(function(name) {
            return {changes_look: name.toLowerCase() === 'color', thumbnails: [], title: name, values: []};
        });
        $('#modal-add-variant-options').modal('hide');
        $("a.add-new-variant").trigger('click');
    }
});

$("a.add-new-variant").click(function (e) {
    e.preventDefault();
    if (!product.options || !product.options.length) {
        $('#modal-add-variant-options').modal('show');
        $('#modal-add-variant-options #product-variant-options').tagit({
            allowSpaces: true,
            availableTags: ['Color', 'Size'],
            placeholderText: 'Enter new options',
        });
        return;
    }

    var uuid = uuidv4();
    product.variants.push({id: uuid, compare_price: '', price: '', sku: '', variant: [], image: ''});

    var row = $('<tr>');
    row.addClass('commercehq-variant');
    row.attr('variant-id', uuid);

    var nameCell = $('<td>');
    nameCell.css('white-space', 'nowrap');
    row.append(nameCell);

    var displayElement = $('<div>');
    displayElement.addClass('variant-name');
    nameCell.append(displayElement);

    displayElement.append(
        '<span data-name="title"></span>'
        // +
        // '<a href="#" class="itooltip edit-variant-name" title="Edit" style="margin-left: 8px;">' +
        // '<i class="fa fa-edit" style="font-size: 18px;"></i>' +
        // '</a>'
    );
    displayElement.hide();

    var editElement = $('<div>');
    editElement.css('display', 'flex');
    editElement.css('align-items', 'center');
    editElement.append(
        '<a href="#" class="itooltip save-variant-name" title="Save" style="margin-right: 8px;">' +
        '<i class="fa fa-check" style="font-size: 18px;"></i>' +
        '</a>'
        // +
        // '<a href="#" class="itooltip cancel-variant-name" title="Cancel" style="margin-right: 8px;">' +
        // '<i class="fa fa-times" style="font-size: 18px;"></i>' +
        // '</a>'
    );
    nameCell.append(editElement);

    var options = [];
    if ($('#variants .variant').length) {
        $('#variants .variant').each(function (i, el) {
            options.push({
                'title': $(el).find('#product-variant-name').val(),
                'values': $(el).find('#product-variant-values').val().split(','),
                'changes_look': $(el).data('changes-look'),
                'thumbnails': $(el).data('thumbnails'),
            });
        });
    }

    var el = $('<div>').addClass('editable-variant-name');
    el.css('display', 'flex');
    el.css('align-items', 'center');
    product.options.forEach(function (option) {
        var select = $('<input>');
        select.css('margin-right', '10px').addClass('form-control').prop('name', option.title).attr('placeholder', option.title);
        // var emptyOption = $('<option>').attr('value', '').text('Select ' + option.title).attr('selected','selected');
        // select.append(emptyOption);
        //
        // option.values.forEach(function (value) {
        //     select.append($('<option>').attr('value', value).text(value));
        // });
        el.append(select);
    });
    editElement.prepend(el);

    var inputs =
        '<td><div class="input-group" style="width:120px">' +
        '<span class="input-group-addon input-sm">$</span>' +
        '<input type="number" name="price" value="" min="0" step="0.1" data-number-to-fixed="2" data-number-stepfactor="100" class="form-control currency" />' +
        '</div></td>' +
        '<td><div class="input-group" style="width:120px">' +
        '<span class="input-group-addon input-sm">$</span>' +
        '<input type="number" name="compare_price" value="" min="0" step="0.1" data-number-to-fixed="2" data-number-stepfactor="100" class="form-control currency" />' +
        '</div></td>' +
        '<td><input class="var-input form-control" type="text" name="sku" value="" style="border-right:1px solid #ddd;width:120px"/></td>';
    row.append(inputs);
    row.append(
        '<td><a href="#" class="itooltip delete-variant" title="Remove" style="margin-right: 8px;">' +
        '<i class="fa fa-times" style="font-size: 18px;"></i>' +
        '</a></td>');

    $('#commercehq-variants tbody').append(row);
});

$('body').on('click', 'tr.commercehq-variant td.add-variant-image', function(e) {
    e.preventDefault();
    $('#modal-add-variant-image #images-row').empty();
    product.images.forEach(function(image) {
        $('#modal-add-variant-image #images-row').append(
            '<div class="col-xs-3">' +
            '<img src="'+ image + '" data-src="'+ image + '" class="unveil add-variant-image-block"/>' +
            '</div>'
        );
    });
    $('#modal-add-variant-image').attr('variant-id', $(this).closest('tr').attr('variant-id'));
    $('#modal-add-variant-image').modal('show');
});

$('#modal-add-variant-image').on('click', '.add-variant-image-block', function(e) {
    var id = $('#modal-add-variant-image').attr('variant-id');
    var img = $('#commercehq-variants tr[variant-id="' + id + '"]').find('.add-variant-image img');
    img.attr('src', $(this).prop('src'));
    img.data('src', $(this).prop('src'));
    if (img.next()) {
        img.next().remove();
    }
    var variant = product.variants.find(function (item) {
        if (item.id === id) {
            return item;
        }
    });
    variant.image = $(this).prop('src');
    $('#modal-add-variant-image').modal('hide');
});

$('body').on('click', 'tr.commercehq-variant .delete-variant', function(e) {
    e.preventDefault();

    var id = $(this).parent().parent().attr('variant-id');
    product.variants = product.variants.filter(function(item) {
        if (item.id !== id) {
            return item;
        }
    });
    $(this).parent().parent().remove();
});

$('body').on('click', 'tr.commercehq-variant .edit-variant-name', function(e){
    e.preventDefault();

    $(this).parent().hide();
    var row = $(this).parent().parent().parent();

    var editElement = $(this).parent().next();
    editElement.show();
    editElement.css('display', 'flex');
    editElement.css('align-items', 'center');

    var options = [];

    if ($('#variants .variant').length) {
        $('#variants .variant').each(function (i, el) {
            options.push({
                'title': $(el).find('#product-variant-name').val(),
                'values': $(el).find('#product-variant-values').val().split(','),
                'changes_look': $(el).data('changes-look'),
                'thumbnails': $(el).data('thumbnails'),
            });
        });
    }

    var id = +row.attr('variant-id');
    if (isNaN(id)) {
        id = row.attr('variant-id');
    }
    var variant = product.variants.find(function (item) {
        if (item.id === id) {
            return item;
        }
    });

    var el = $('<div>');
    el.css('display', 'flex');
    el.css('align-items', 'center');
    options.forEach(function (option) {
        var select = $('<select>');
        select.css('margin-right', '10px');
        select.addClass('form-control');
        select.prop('name', option.title);
        var emptyOption = $('<option>').attr('value', '').text('Select ' + option.title).attr('selected', 'selected');
        select.append(emptyOption);

        var selectedValue = null;
        option.values.forEach(function (value) {
            select.append($('<option>').attr('value', value).text(value));
            if (variant.variant.includes(value)) {
                selectedValue = value;
            }
        });
        if (selectedValue) {
            select.val(selectedValue);
        }
        el.append(select);
    });

    editElement.prepend(el);
});

$('body').on('click', 'tr.commercehq-variant .cancel-variant-name', function(e) {
    e.preventDefault();

    $(this).parent().prev().show();
    $(this).prev().prev().remove();
    $(this).parent().hide();
});

$('body').on('click', 'tr.commercehq-variant .save-variant-name', function(e) {
    e.preventDefault();

    var el = $(this).prev();
    var editElement = $(this).parent();
    var displayElement = $(this).parent().prev();

    var row = $(this).parent().parent().parent();
    var variant = {variant: []};
    var id = +row.attr('variant-id');
    if (isNaN(id)) {
        id = row.attr('variant-id');
    }
    variant = product.variants.find(function (item) {
        if (item.id === id) {
            return item;
        }
    });

    var title = '';
    variant.variant = [];
    editElement.find('input').each(function() {
        var value = $(this).val();
        if (value) {
            variant.variant.push(value);
            if (title) {
                title += ' / ' + value;
            } else {
                title = value;
            }
        }
    });

    displayElement.find('span').text(title);

    displayElement.show();
    el.remove();
    editElement.hide();
});

function removeVariant(e) {
    e.preventDefault();

    var removedOptions = $('#product-variant-values', $(e.target).parent()).val().split(',');

    product.variants.forEach(function (item) {
        item.variant = item.variant.filter(function (variant) {
            if (!removedOptions.includes(variant)) {
                return variant;
            }
        });
    });

    removedOptions.forEach(function (option) {
        $('#commercehq-variants tr.commercehq-variant').each(function (j, tr) {
            $('span[data-name="title"]', tr).text($('span[data-name="title"]', tr).text().replace(option, '').replace(/\s\/\s$/, '').replace(/^\s\/\s/, ''));
        });
    });

    $(e.target).parent().remove();
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
        'options': product.options,
    };

        $('#commercehq-variants tr.commercehq-variant').each(function(j, tr) {

            var variant_data = {};
            var id = +$(tr).attr('variant-id');
            if (!isNaN(id)) {
                variant_data.id = parseInt($(tr).attr('variant-id'));
            }

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

            var title = $('span[data-name="title"]', tr).text();
            if (title) {
                variant_data.variant = title.split(' / ');
            } else {
                variant_data.variant = [];
            }

            variant_data.variant.forEach(function(option, index) {
                if (!api_data.options[index].values.includes(option)) {
                    api_data.options[index].values.push(option);
                }
            });

            api_data.variants.push(variant_data);
        });

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
                  toastr.success('The variants are now split into new products.\r\n' +
                    'The new products will get connected to shopify very soon.', 'Product Split!');
                } else {
                  toastr.success('The variants are now split into new products.', 'Product Split!');
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
    var imageID = $(e.target).parents('.var-image-block').find('img').attr('image-id');
    var new_images = [];

    for (var i = 0; i < product.images.length; i++) {
        if (i != imageID) {
            new_images.push(product.images[i]);
        }
    }

    product.images = new_images;
    $(e.target).parent().remove();

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

$('.parent-product-disconnect').click(function(e) {
    var btn = $(this);
    btn.bootstrapBtn('loading');

    $.ajax({
        url: api_url('disconnect-parent-product', 'multichannel'),
        type: 'POST',
        data: JSON.stringify({
            'product': config.product_id,
            'store_type': 'chq',
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
            'store_type': 'chq',
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
            store_type: 'chq',
        },
        success: function (data) {
            if ('product' in data) {
                if (config.connected) {
                    var channel_event = 'product-update';
                    var pusher = new Pusher(data.product.pusher.key);
                    var channel = pusher.subscribe(data.product.pusher.channel);

                    channel.bind(channel_event, function (data) {
                        if (data.progress) {
                            return;
                        }
                        pusher.unsubscribe(channel);
                        if (data.success) {
                            window.location.hash = 'connections';
                            window.location.reload();
                        } else {
                            $('.parent-product-link').bootstrapBtn('reset');
                            displayAjaxError('Link Product', data, true);
                        }
                    });
                } else {
                    window.location.hash = 'connections';
                    window.location.reload();
                }
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
