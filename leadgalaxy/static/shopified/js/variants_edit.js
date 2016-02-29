/* global $, toastr, swal, displayAjaxError, api_url, product */

(function(api_url, product) {
'use strict';

$('#btn-variants-img').click(function(e) {
    localStorage.current_product = JSON.stringify(document.savedProduct);
    //window.location.href='/variants.html';
});

function updateSelectButton() {
    var current = parseInt($('.current-var').val());
    var total = $('.current-var').prop('total');

    $('.var-btn-prev').prop('disabled', current <= 0);
    $('.var-btn-next').prop('disabled', current + 1 >= total);
}

$('.var-btn-next').click(function(e) {
    var current = parseInt($('.current-var').val());
    var total = $('.current-var').prop('total');
    var next = current + 1;

    if (next < product.variants.length) {
        $('.current-var').val(next);
    }

    updateSelectButton();
});

$('.var-btn-prev').click(function(e) {
    var current = parseInt($('.current-var').val());
    var total = $('.current-var').prop('total');
    var next = current - 1;

    if (next >= 0) {
        $('.current-var').val(next);
    }

    updateSelectButton();
});

$('#view-btn').click(function(e) {
    var url = api_url.replace(/\/[^:]+:[^@]+@/, '/');
    window.open(url + '/admin/products/' + product.id, '_blank');
});

function imageClicked(e) {
    var img = $(this);
    var current = $('.current-var').val();
    var variant_id = product.variants[current].id;
    var image_id = $(this).attr('image-id');

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
        url: '/api/variant-image',
        type: 'POST',
        data: {
            'url': api_url + '/admin/variants/' + variant_id + '.json',
            'data': JSON.stringify(api_data)
        },
        context: {
            image: this
        },
        success: function(data) {
            if (data.status == 'ok') {
                img.parent().find('.link-success').fadeIn();
                setTimeout(function() {
                    img.parent().find('.link-success').fadeOut();
                }, 1500);
            } else {
                displayAjaxError('Image linking error', data);
            }
        },
        error: function(data) {
            displayAjaxError('Image linking error', data);
        },
        complete: function() {
            img.parent().loader('hide');
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
                text: product.variants[i].title,
                value: i
            }));
        });

        $.each(product.images, function(i, el) {
            var d = $('<div>', {
                'class': 'col-xs-3 var-image-block'
            });

            var img = $('<img>', {
                src: el.src,
                'class': 'var-image',
                'image-id': el.id
            });

            d.append(img);
            d.append($('<img class="link-success" src="http://shopifiedapp.s3.amazonaws.com/static/img/checked-checkbox-24.png" ' +
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
})(api_url, product);
