function ajaxify_label(file) {
    $('#mockup-link').html('');
    var url = api_url('ajaxify-label', 'supplements');
    var form = document.getElementById('user_supplement_form');
    if (file !== undefined) {
        var p = new Promise(function(resolve, reject) {
            getImageUrl(form, file, submit=false).then(function() {
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
    $('#sample_label').on('click', function(e) {
        if (form.checkValidity()) {
            e.preventDefault();
            $(this).attr('data-send-to-store', 'true');
            $('#modal-send-to-store').modal({backdrop: 'static', keyboard: false});
        }
    });

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
