(function(config, product) {

    'use strict';
    $('.remove-background-image-editor').click(function(e) {
        e.preventDefault();

        var image = $(this).siblings('img');
        if (config.clipping_magic.clippingmagic_editor && !config.clipping_magic.stripe_customer) {
            if (!$.trim(config.clipping_magic.api_id).length || !$.trim(config.clipping_magic.api_secret).length) {
                $('#modal-clippingmagic').modal('show');
                return;
            }
        } else if ( !config.clipping_magic.clippingmagic_editor ) {
            swal('Clipping Magic', "You haven't subscribe for this feature", 'error');
            return;
        }

        $.ajax({
            url: '/api/clippingmagic-clean-image',
            type: 'POST',
            data: {
                api_id: config.clipping_magic.api_id,
                api_secret: config.clipping_magic.api_secret,
                image_url: image.attr('src'),
                product_id: config.product_id,
                action: 'edit',
            }
        }).done(function(data) {
                if ( data.status == 'ok' )
                    edit_image( data, image )
                else
                    swal({title: "Error", text: data.msg, type: "error", html: true, closeOnConfirm: true, animation: false, confirmButtonText: "Ok"});
        }).fail(function(data) {
            displayAjaxError('Clipping Magic', data);
        });
    });

    $('#save-clippingmagic').click(function() {
        if (!$("#modal-clippingmagic .api_id").val().trim().length ||
            !$("#modal-clippingmagic .api_key").val().trim().length) {
            swal('Clipping Magic', 'Please enter required fields.', 'error');
            return;
        }

        var btn = $(this);
        btn.bootstrapBtn('loading');

        $.ajax({
            url: '/api/user-clippingmagic',
            type: 'POST',
            data: $('form#user-clippingmagic').serialize(),
            context: {
                btn: btn
            }
        }).done(function(data) {
            $('#modal-clippingmagic').modal('hide');
            window.location.reload();

        }).fail(function(data) {
            displayAjaxError('Clipping Magic', data);

        }).always(function() {
            this.btn.bootstrapBtn('reset');
        });
    });

    function edit_image(data, image) {
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
                        api_id: config.clipping_magic.api_id,
                        api_secret: config.clipping_magic.api_secret,
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
                            clippingmagic: config.clipping_magic.clippingmagic_editor,
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

})(config, product);