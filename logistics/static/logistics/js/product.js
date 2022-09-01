var variantTemplate = Handlebars.compile($('#variant').html());
var lastVariantID = $('.variant').length;
var groupTpl = Handlebars.compile($("#variant-group").html());

$(document).on('ready', function() {
    JSON.parse($('[name="variants_map"]').val()).forEach(function(variantType) {
        variantType.sku = '';
        variantType.values = variantType.values.map(function(v) {
            if (v.sku.indexOf(':') > -1) {
                var skus = v.sku.split(':');
                v.sku = skus[1];
                variantType.sku = skus[0];
            }
            return v;
        });
        $('#variant-groups').append(groupTpl(variantType));
    });

    for (var i = 0, iLength = variants.length; i < iLength; i++) {
        if (!isNaN(variants[i].length)) {
            variants[i].length = parseFloat(variants[i].length);
        }
        if (!isNaN(variants[i].width)) {
            variants[i].width = parseFloat(variants[i].width);
        }
        if (!isNaN(variants[i].height)) {
            variants[i].height = parseFloat(variants[i].height);
        }

        $('#variants').append(variantTemplate({'variant': variants[i], 'config': userConfig}));
    }

    joinVariants(formatVariants());
});

$('#variants').on('keyup', '[name^="variant_title_"]', function() {
    var variantId = $(this).parents('.variant').find('[name="variant_ids"]').val();
    var text = $(this).val();
    $('[data-variant-id="' + variantId + '"] ').text(text).attr('title', text);
});

$('#add-variant').on('click', function(e) {
    e.preventDefault();
    $('#variant-groups').append(groupTpl());
});

$('#variant-groups').on('click', '.variant-group-add-values', function(e) {
    e.preventDefault();
    var groupValueTpl = Handlebars.compile($("#variant-group-value").html());
    $(this).parents('.variant-group').find('.variant-group-values').append(groupValueTpl());
});

$('#variant-groups').on('click', '.close', function(e) {
    e.preventDefault();
    $(this).parents('.variant-group').remove();
    var variantsMap = formatVariants();
    $('[name="variants_map"]').val(JSON.stringify(variantsMap));
    joinVariants(variantsMap);
});

$('#variant-groups').on('change', 'input', function() {
    var variantsMap = formatVariants();
    $('[name="variants_map"]').val(JSON.stringify(variantsMap));
    joinVariants(variantsMap);
});


$('#variants').on('click', '.variant .close', function(e) {
    e.preventDefault();
    var wrapper = $(this).parents('.variant');
    $('#variants').append(wrapper.find('[name="variant_ids"]'));
    wrapper.remove();
});

function cartesianProduct(arr) {
    if (!arr.length) {
        return [];
    }
    return arr.reduce(function(a,b){
        return a.map(function(x){
            return b.map(function(y){
                return x.concat([y]);
            });
        }).reduce(function(a,b){ return a.concat(b); },[]);
    }, [[]]);
}

function updateBySku(variant) {
    var parent = null;
    if (variant.sku) {
        var skuElem = $('[name^="variant_sku_"][value="' + variant.sku + '"]');
        if (skuElem.length) {
            parent = skuElem.parents('.variant');
            parent.find('.variant-label').text(variant.label);
            skuElem.siblings('[name^="variant_title_"]').val(variant.title);
            return parent.find('[name="variant_ids"]').val();
        }
    }
    if (variant.title) {
        var titleElem = $('[name^="variant_title_"][value="' + variant.title + '"]');
        if (titleElem.length) {
            parent = titleElem.parents('.variant');
            parent.find('.variant-label').text(variant.label);
            titleElem.siblings('[name^="variant_sku_"]').val(variant.sku);
            return parent.find('[name="variant_ids"]').val();
        }

        var variantId = null;
        $('[data-variant-id]').each(function() {
            if (variant.title === $(this).text()) {
                variantId = $(this).attr('data-variant-id');
                $('#variants').append(variantTemplate({
                    'variant': $.extend({weight: 0, height: 0, width: 0, length: 0}, variant, {'id': variantId}),
                    'config': userConfig,
                }));
            }
        });
        if (variantId) {
            return variantId;
        }
    }

    return false;
}

// var variantsMap = [{"title": "Color", "values": [{"title": "Grey", "image": "https://sc04.alicdn.com/kf/Hd44d78f01e79433ea3aef44e7056c1df4.jpg_100x100.jpg", "sku": "191288010:3483425"}, {"title": "KHAKI", "image": "https://sc04.alicdn.com/kf/Ha3ad4aa46cf44cf8ae86407e41e86fe5p.jpg_100x100.jpg", "sku": "191288010:-1"}, {"title": "Black", "image": "https://sc04.alicdn.com/kf/H9b0917e171b14fc69be814e7e9d9ed55X.jpg_100x100.jpg", "sku": "191288010:3327837"}]}, {"title": "Shoe US Size", "values": [{"title": "10", "image": null, "sku": "210232962:27438"}, {"title": "9", "image": null, "sku": "210232962:3234815"}, {"title": "7.5", "image": null, "sku": "210232962:3417294"}, {"title": "10.5", "image": null, "sku": "210232962:3892861"}, {"title": "7", "image": null, "sku": "210232962:27435"}, {"title": "8", "image": null, "sku": "210232962:27436"}]}];
function formatVariants() {
    var variantsMap = [];
    $('.variant-group').each(function() {
        var variant = {values: []};
        var parentSku = $(this).find('[name="group_sku"]').val();
        variant.title = $(this).find('[name="group_title"]').val() || '';
        variant.sku = parentSku;

        $(this).find('.variant-group-value').each(function() {
            var title = $(this).find('[name="value_title"]').val();
            var sku = $(this).find('[name="value_sku"]').val();
            if (title || sku) {
                if (parentSku) {
                    sku = sku ? parentSku + ':' + sku : '';
                }
                variant.values.push({
                    'title': title,
                    'sku': sku,
                });
            }
        });
        variantsMap.push(variant);
    });
    return variantsMap;
}

function joinVariants(variantsMap) {
    var existingIds = [];
    variantsMap = variantsMap.map(function(v) { return v.values; }).filter(function(v) { return v.length > 0; });
    cartesianProduct(variantsMap).forEach(function(variants) {
        variant = {title: [], sku: []};
        variants.forEach(function(v) {
            if (v.title) {
                variant.title.push(v.title);
            }
            if (v.sku) {
                variant.sku.push(v.sku);
            }
        });
        variant.title = variant.title.join(' / ');
        variant.sku = variant.sku.join(';');

        variant.label = [];
        if (variant.title) {
            variant.label.push(variant.title);
        }
        if (variant.sku) {
            variant.label.push(variant.sku);
        }
        variant.label = variant.label.join(' - ');

        var variantId = updateBySku(variant);
        if (!variantId) {
            lastVariantID += 1;
            variantId = lastVariantID * -1;
            $('#variants').append(variantTemplate({
                'variant': $.extend({}, variant, {'id': variantId}),
                'config': userConfig,
            }));
        }
        existingIds.push(variantId + '');
    });

    $('[name="variant_ids"]').each(function() {
        if (existingIds.indexOf($(this).val()) === -1) {
            var variant = $(this).parents('.variant');
            $(this).appendTo($('#variants'));
            variant.remove();
        }
    });
}
