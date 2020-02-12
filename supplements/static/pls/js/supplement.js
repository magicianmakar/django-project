$(document).ready(function(){
    var reader = new FileReader();
    var form = document.getElementById('user_supplement_form');

    function getImageUrl() {
        var file = form.upload.files[0];
        var p = new Promise(function(resolve, reject) {
            reader.onload = function() {
                if (!(reader.result.includes('application/pdf'))) {
                    return reject('Invalid file type');
                }
                pdfjsLib.getDocument(reader.result).promise.then(function(pdf) {
                    pdf.getPage(1).then(function(page) {
                        var viewport = page.getViewport({scale: 3});

                        var canvas = document.getElementById('canvas');
                        canvas.width = viewport.width;
                        canvas.height = viewport.height;
                        var context = canvas.getContext('2d');

                        var renderContext = {
                            canvasContext: context,
                            viewport: viewport
                        };

                        var renderTask = page.render(renderContext);
                        renderTask.promise.then(function() {
                            var url = canvas.toDataURL();
                            resolve(url);
                        });
                    });
                });
            };
        });
        reader.readAsDataURL(file);

        p.then(function(url) {
            form.image_data_url.value = url;
            form.submit();
        }).catch(function (reason) {
              $("form input[type=submit]").button('reset');
              toastr.error('Only "pdf" file is allowed');
        });
    }

    $('.product-images').slick({
        dots: true
    });

    $('#user_supplement_form input[type=submit]').click(function() {
        var action = $(this).data('action');
        form.action.value = action;

        if (action === 'approve') {
            getImageUrl();
            return false;
        }
    });
});
