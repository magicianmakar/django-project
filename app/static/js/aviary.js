function launchEditor(image) {
    if (config.photo_editor !== null) {
        var imageUrl = app_link(['api/ali/get-image'], {
            url: image.src
        });

        imageUrl = imageUrl.replace(/^https?:\/\/dev.dropified.com(:[0-9]+)?/, 'https://app.dropified.com');  // Make it work in dev

        // Maintain current image source
        var editorImage = new Image();
        editorImage.setAttribute('src', imageUrl);
        editorImage.setAttribute('image-id', image.getAttribute('image-id'));

        feather_editor.launch({'image': editorImage});
    } else {
        swal('Image Editor', 'Please upgrade your plan to use this feature.', 'warning');
    }
}

var feather_editor = new Aviary.Feather({
    apiKey: 'f94fd6b3b91f5e3c52aec692de8919cf',
    theme: 'dark',
    tools: [
        'crop', 'resize', 'orientation', 'draw', 'enhance', 'brightness',
        'contrast', 'saturation', 'warmth', 'whiten', 'focus', 'vignette',
        'sharpness', 'colorsplash', 'blemish', 'redeye', 'text', 'meme',
    ],
    enableCORS: true,
    fileFormat: 'png',
    onSave: function(imageID, newURL) {},
    onError: function(errorObj) {
        alert(errorObj.message);
    }
});

// Image saving callback
window.asi = function(img, blob, imageBytes, type) {
    feather_editor.disableControls();
    feather_editor.showWaitIndicator();

    var imageID = $(img).attr('image-id');
    var oldURL = $(img).attr('src');
    var newURL = URL.createObjectURL(blob) + '.png';

    var fd = new FormData();
    fd.append('image', blob);
    fd.append('product', config.product_id);
    fd.append('old_url', oldURL);
    fd.append('url', newURL);

    var storeType = window.location.href.match('(chq|woo|gear|gkart|bigcommerce|ebay|fb)');
    if (storeType) {
        fd.append(storeType[0], 1);
    }

    $.ajax({
        url: '/upload/save_image_s3',
        type: 'POST',
        data: fd,
        context: {'imageID': imageID},
        processData: false,
        contentType: false,
        success: function(data) {
            $('#product-image-' + imageID).prop('src', data.url);
            window.product.images[imageID] = data.url;
            linkNewUrlToOldImage($('#product-image-' + imageID), data.url);


            if (window.asic) { // Send new url to the editor
                window.asic(data.url);
            }

            feather_editor.close();

            toastr.info("Image was saved successfully.");
        },
        error: function(data) {
            toastr.error('Image could not be created, please try again.');
        },
        complete: function() {
            feather_editor.enableControls();
            feather_editor.hideWaitIndicator();
        }
    });
};

if (!window.config) {
    // Make sure that config exists.
    window.config = {};
}

config.old_to_new_url = {};  // This stores link from old to new image urls.

var linkNewUrlToOldImage = function (image, newUrl) {
    var originalUrl = image.attr('image-url');
    config.old_to_new_url[originalUrl] = newUrl;
};
