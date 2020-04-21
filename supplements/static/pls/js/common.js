function getImageUrl(form, file, submit) {
    var reader = new FileReader();
    submit = submit === undefined ? true : false;
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
        if (submit) {
            form.submit();
        }
    }).catch(function (reason) {
          $("form input[type=submit]").button('reset');
          toastr.error('Only PDF file is allowed');
    });

    return p;
}

$(document).ready(function(){
    $('.custom-file-input').on('change', function() {
        var fileName = $(this).val().split('\\').pop();
        var nextLabel = $(this).next('.custom-file-label');

        if (fileName !== '') {
          nextLabel.addClass("selected").html(fileName.substring(0, 27));
        } else {
          nextLabel.html(nextLabel.data('placeholder'));
        }
    });

    $("input[type='reset']").closest('form').on('reset', function() {
        $('.custom-file-label').each(function (i, el) {
            $(el).html($(el).data('placeholder'));
        });

        var commentField = CKEDITOR.instances['id_comment'];
        if (commentField) {
            commentField.setData('');
        }
    });

    $(".pls-reset-btn").click(function () {
        $(".form-control").each(function (i, item) {
            $(item).val('');
        });
    });

    $(".download-label").click(function () {
        var item = $(this).data('item-id');
        var url = api_url('mark-printed', 'supplements');
        data = {'item-id': item};
        $.ajax({
            url: url,
            type: "POST",
            data: JSON.stringify(data),
            dataType: 'json',
            contentType: 'application/json',
        });
    });

    $(".add-loader").click(function () {
        if ($(this).parents('form')[0].checkValidity()) {
            $(this).button('loading');
        }
    });

    $("#print-all-labels").click(function (e) {
        e.preventDefault();
        var data = {'item-ids': []};
        $(".line-checkbox").each(function (i, item) {
            if ($(item).prop('checked')) {
                data['item-ids'].push($(item).data("id"));
            }
        });
        if (data['item-ids'].length === 0) {
            toastr.info("Please select line items to print labels against.");
            return;
        }

        $("#print-message").html("Processing...");
        var url = api_url('bulk-print', 'supplements');
        $.ajax({
            url: url,
            type: "POST",
            data: JSON.stringify(data),
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                var url = response['download-url'];
                var link = "<a href='" + url + "' target='_blank'>Download All</a>";
                $("#print-message").html(link);
            }
        });
    });

    $("#mark-all-labels").click(function (e) {
        e.preventDefault();
        var data = {'item-ids': []};
        $(".line-checkbox").each(function (i, item) {
            if ($(item).prop('checked')) {
                data['item-ids'].push($(item).data("id"));
            }
        });
        if (data['item-ids'].length === 0) {
            toastr.info("Please select line items to mark labels against.");
            return;
        }

        var url = api_url('bulk-mark', 'supplements');
        $.ajax({
            url: url,
            type: "POST",
            data: JSON.stringify(data),
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                toastr.success("Successfully marked selected lines as printed.");
            }
        });
    });

    $("#select-all-lines").click(function () {
        $('.line-checkbox').prop('checked', $(this).prop('checked'));
    });

    $("#id_shipping_countries").chosen();
});
