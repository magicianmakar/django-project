var mockupData = {};

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
          toastr.error('Only PDF file is allowed');
    });

    return p;
}

function ajaxify_label(file) {
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
                        $('.loader').hide();
                        for (var key in response.data) {
                            $('#'+key).attr('src', response.data[key]);
                        }
                        $('#save-mockups').prop('disabled', false);
                        $('.preview-text').html('Click on any image to preview it here');
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
                if (fileUrl !== "" && Object.keys(mockupData).length === 0) {
                    toastr.info("Please select at least 1 or more mockup images to send to store.");
                } else if (fileUrl === "" && labelUrl === "") {
                    toastr.error('A PDF label is required to submit a product for approval');
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
                if (fileUrl !== "" && Object.keys(mockupData).length === 0) {
                    toastr.info("Please select at least 1 or more mockup images to send to store.");
                } else {
                    form.submit();
                }
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

    $('.img-select-opt').click(function () {
      if ($(this).html() === 'SELECT ALL') {
          $('.mockup-select').prop('checked', true);
      } else {
          $('.mockup-select').prop('checked', false);
      }
    });

    $('.mockup-img').click(function () {
        $('.preview-text').addClass('hidden');
        $('#mockup-preview').attr('src', $(this).attr('src'));
    });

    $('#save-mockups').click(function (e) {
        e.preventDefault();
        mockupData = {};
        $(".mockup-select").each(function (i, item) {
            if ($(item).prop('checked')) {
                var img = $(item).next('img');
                mockupData[img.attr('id')] = img.attr('src');
            }
        });
        if (Object.keys(mockupData).length === 0) {
            toastr.info("Please select at least 1 or more mockup images to send to store.");
            return;
        } else {
            form.mockup_data.value = JSON.stringify(mockupData);
            $('#modal-mockup-images').modal('hide');
        }
    });

});
