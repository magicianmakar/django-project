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

    var storeType = window.location.href.match('(chq|woo|gear|gkart)');
    if (storeType) {
        formData.append(storeType[0], 1);
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