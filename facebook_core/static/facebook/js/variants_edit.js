/* global $, config, toastr, swal, displayAjaxError, api_url, product, Pusher */

(function(api_url, product, store_id, config) {
'use strict';

$('#btn-variants-img').click(function(e) {
    localStorage.current_product = JSON.stringify(document.savedProduct);
    //window.location.href='/variants.html';
});

function verifyPusherIsDefined() {
    if (typeof(Pusher) === 'undefined') {
        toastr.error('This could be due to using Adblocker extensions<br>' +
            'Please whitelist Dropified website and reload the page<br>' +
            'Contact us for further assistance',
            'Pusher service is not loaded', {timeOut: 0});
        return false;
    }
    return true;
}

function updateSelectButton() {
    var current = parseInt($('.current-var').val(), 10);
    var total = $('.current-var').prop('total');
    var variant_id = product.variants[current].id;
    var image_id = product.variants[current].image_id;
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
    var variant_guid = product.variants[current].guid;
    var parent_guid = product.guid;
    var image_id = img.attr('image-id');
    var image_src = img.attr('src');

    $('.var-btn-prev').prop('disabled', true);
    $('.var-btn-next').prop('disabled', true);

    var api_data = {
        "variant": {
            "id": variant_id,
            "image_id": image_id,
        }
    };

    img.parent().loader('show');

    if (!verifyPusherIsDefined()) {
        return;
    }
    var pusher = new Pusher(config.sub_conf.key);
    var channel = pusher.subscribe(config.sub_conf.channel);

    channel.bind('product-update', function(eventData) {
        if (eventData.product === product.guid) {
            if (eventData.progress) {
                btn.text(eventData.progress);
                return;
            }

            pusher.unsubscribe(channel);

            if (eventData.success) {
                toastr.success('Variant image of product updated.','Facebook Update');
                img.parent().loader('hide');
                product.variants[current].image_id = image_id;

                $('.link-success').hide();
                img.parent().find('.link-success').fadeIn();

                if ($('#auto-next').prop('checked')) {
                    $('.var-btn-next').trigger('click');
                }
            }
            if (eventData.error) {
                displayAjaxError('Update variant image of product', eventData, true);
            }
        }
    });

    channel.bind('pusher:subscription_succeeded', function() {
        $.ajax({
            url: '/api/fb/variant-image',
            type: 'POST',
            data: {
                'store': store_id,
                'variant_id': variant_id,
                'variant_guid': variant_guid,
                'parent_guid': parent_guid,
                'image_id': image_id,
                'image_src': image_src,
            },
            success: function (data) {},
            error: function (data) {
                pusher.unsubscribe(channel);
                displayAjaxError('Update variant image of product', data);
            }
        });
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
            d.append($('<img class="link-success" src="//cdn.dropified.com/static/img/checked-checkbox-24.png" ' +
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
})(api_url, product, store_id, config);
