function getImageUrl(file, submit) {
    var reader = new FileReader();
    var form = document.getElementById('user_supplement_form');
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
          toastr.error('Only "pdf" file is allowed');
    });

    return p;
}

function ajaxify_label(file) {
    $('#mockup-link').html('');
    var url = api_url('ajaxify-label', 'supplements');
    var form = document.getElementById('user_supplement_form');
    if (file !== undefined) {
        var p = new Promise(function(resolve, reject) {
            getImageUrl(file, submit=false).then(function() {
                data = {
                    'image_data_url': form.image_data_url.value,
                    'mockup_slug': form.mockup_slug.value,
                };
                $.ajax({
                    url: url,
                    type: "POST",
                    data: JSON.stringify(data),
                    dataType: 'json',
                    contentType: 'application/json',
                    success: function (response) {
                        $('#mockup').attr('src', response['data_url']);
                        var link = "<a href='#' data-toggle='modal' data-target='#modal-preview-image'>Preview</a>";
                        $('#mockup-link').html(link);
                    }
                });
            }).catch(function (reason) {
                  console.log(reason);
            });
      });
    }
}

$(document).ready(function(){
    var form = document.getElementById('user_supplement_form');

    $('.product-images').slick({
        dots: true
    });

    $('.confirm-create').click(function(e) {
        var button = $(this);
        var action = button.data('action');
        var labelUrl = button.data('label-url');
        form.action.value = action;

        if (form.checkValidity()) {
            e.preventDefault();
            var fileUrl = form.image_data_url.value;
            if (action === 'approve') {
                if (fileUrl === "" && labelUrl === undefined) {
                    toastr.error('A "pdf" label file is required in case of submitting for approval.');
                } else {
                    swal({
                        title: "Are you sure?",
                        text: "You are about to send this product label for approval and won’t be able to make changes until your product is approved, please ensure your label meets all guidelines.",
                        type: "warning",
                        showCancelButton: true,
                        confirmButtonColor: '#79aa63',
                        cancelButtonColor: '#ed5565',
                        confirmButtonText: "Submit for Approval",
                      },
                      function(isConfirm){
                          if (isConfirm) {
                              if(fileUrl !== "") {
                                  form.submit();
                              } else {
                                  if (labelUrl) {
                                      form.image_data_url.value = labelUrl;
                                      form.submit();
                                  }
                              }
                          }
                      });
                }
            } else {
                form.submit();
            }
        }
    });

    $('#save-changes').click(function (e) {
        e.preventDefault();
        var fileUrl = form.image_data_url.value;
        if (fileUrl !== "") {
            form.action.value = 'approve';
        } else {
            form.action.value = 'save';
        }
        form.submit();
    });

});
