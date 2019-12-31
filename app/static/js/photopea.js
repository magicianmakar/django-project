(function(config) {
    var pusherSubscription = false;

    window.createPhotopeaURL = function(image, imageId) {
        var imageUrl = app_link(['api/ali/get-image'], {
            url: image
        });

        imageUrl = imageUrl.replace(/^https?:\/\/dev.dropified.com(:[0-9]+)?/, 'https://app.dropified.com'); // Make it work in dev

        var serverUrl = app_link('/upload/save_image_s3') + '?' + $.param({
            token: config.token,
            image_id: imageId,
            product: config.product_id,
            advanced: true,
            old_url: image,
            url: imageId + '.jpg'
        });

        var storeType = window.location.href.match('(chq|woo|gear|gkart|bigcommerce)');
        if (storeType) {
            serverUrl += '&' + storeType[0] + '=1';
        }

        var photoPeaConfig = encodeURI(JSON.stringify({
            "files": [imageUrl],
            "server": {
                "version": 1,
                "url": serverUrl,
                "formats": ["jpg"]
            },
            "environment": {
                "theme": 2,
                "vmode": 0,
                "localsave": true,
                "script": "app.activeDocument.resizeCanvas(90,80,AnchorPosition.TOPLEFT);"
            }
        }));

        return 'https://www.photopea.com#' + photoPeaConfig;
    };

    function subscribeToPusher() {
        if (pusherSubscription) {
            return;
        }

        if (!window.pusher || !window.channel) {
            window.pusher = new Pusher(config.sub_conf.key);
            window.channel = window.pusher.subscribe(config.sub_conf.channel);
        }

        window.channel.bind('advanced-editor', function(data) {
            if (data.product == config.product_id) {

                if (data.success) {
                    setTimeout(function() {
                        var image = $('#' + data.image_id);
                        image.attr('src', data.url);
                        product.images[parseInt(image.attr('image-id'), 10)] = data.url;
                        document.linkNewUrlToOldImage(image, data.url);
                    }, 500);
                } else {
                    displayAjaxError('Advanced Editor', data);
                }
            }
        });

        pusherSubscription = true;
    }

    $('#var-images').on('click', '.advanced-edit-photo', function(e) {
        var image = $(this).parents('.var-image-block').find('img');
        var imageId = image.attr('id');
        var imageSrc = image.attr('src');
        window.open(createPhotopeaURL(imageSrc, imageId));

        subscribeToPusher();
    });

})(config);
