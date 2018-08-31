/* global $, toastr, swal, displayAjaxError, api_url, product */

(function(product, store_id) {
'use strict';

$('#btn-variants-img').click(function(e) {
    localStorage.current_product = JSON.stringify(document.savedProduct);
    //window.location.href='/variants.html';
});

function updateSelectButton() {
    var current = parseInt($('.current-var').val(), 10);
    var total = $('.current-var').prop('total');
    var variant_id = product.variants[current].id;
    var image_id = product.variants[current].image.id;
    var img = $('img[image-id='+image_id+']');

    $('.link-success').hide();
    $('.link-success', img.parent()).show();

    $('.var-btn-prev').prop('disabled', current <= 0);
    $('.var-btn-next').prop('disabled', current + 1 >= total);
}

$('.var-btn-next').click(function(e) {
    var current = parseInt($('.current-var').val(), 10);
    var total = $('.current-var').prop('total');
    var next = current + 1;

    if (next < product.variants.length) {
        $('.current-var').val(next);
    }

    updateSelectButton();
});

$('.var-btn-prev').click(function(e) {
    var current = parseInt($('.current-var').val(), 10);
    var total = $('.current-var').prop('total');
    var next = current - 1;

    if (next >= 0) {
        $('.current-var').val(next);
    }

    updateSelectButton();
});

function imageClicked(e) {
    var img = $(e.target);
    var current = $('.current-var').val();
    var variant_id = product.variants[current].id;
    var image_id = img.attr('image-id');
    var product_id = product.id;

    $('.var-btn-prev').prop('disabled', true);
    $('.var-btn-next').prop('disabled', true);

    var api_data = {
        "variant": {
            "id": variant_id,
            "image_id": image_id,
        }
    };

    img.parent().loader('show');

    $.ajax({
        url: api_url('variant-image', 'woo'),
        type: 'POST',
        data: {
            'product': product_id,
            'store': store_id,
            'variant': variant_id,
            'image': image_id
        },
        context: {
            image: img,
            current: current,
            image_id: image_id,
        },
        success: function(data) {
            product.variants[this.current].image.id = this.image_id;

            $('.link-success').hide();
            this.image.parent().find('.link-success').fadeIn();

            if ($('#auto-next').prop('checked')) {
                $('.var-btn-next').trigger('click');
            }
        },
        error: function(data) {
            displayAjaxError('Image linking error', data);
        },
        complete: function() {
            this.image.parent().loader('hide');
        }
    });

    updateSelectButton();
}

function setupVariantsLinking() {
    $('.product-title').text(product.title);
    $('.product-variants').text(product.variants.length);

    if (product.variants.length) {
        $('.current-var').prop('total', product.variants.length);

        $.each(product.variants, function(i, el) {
            $('.current-var').append($('<option>', {
                text: product.variants[i].description.replace(/<.*?>/g, ''),
                value: i
            }));
        });

        $.each(product.images, function(i, el) {
            if (i !== 0 && i % 4 === 0) {
                $('#var-images').append($('<div class="col-md-12"></div>'));
            }

            var d = $('<div>', {
                'class': 'col-md-3 var-image-block'
            });

            var img = $('<img>', {
                src: el.src,
                'class': 'var-image',
                'image-id': el.id
            });

            d.append(img);
            d.append($('<img class="link-success" src="//d2kadg5e284yn4.cloudfront.net/static/img/checked-checkbox-24.png" ' +
                'style="display:none;position: absolute;left: 25px;' +
                'top: 5px;background-color: #fff;border-radius: 5px;">'
            ));

            img.click(imageClicked);

            $('#var-images').append(d);
        });

        updateSelectButton();

        $('.current-var').change(updateSelectButton);
    }
}

$(function() {
    setupVariantsLinking();
});
})(product, store_id);
