var mockupData = {};

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
        form.action.value = action;

        if (form.checkValidity()) {
            e.preventDefault();
            var fileUrl = form.upload_url.value;
            var labelUrl = button.data('label-url');
            if (action === 'approve') {
                if (fileUrl === "" && (labelUrl === undefined || labelUrl === "")) {
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
                            form.submit();
                          }
                      });
                }
            } else {
                if (fileUrl !== "" && $('[name="mockup_urls"]').length === 0) {
                    toastr.info("Please select at least 1 or more mockup images to send to store.");
                } else {
                    form.submit();
                }
            }
        }
    });

    $('.img-select-opt').click(function () {
      if ($(this).html() === 'SELECT ALL') {
          $('.mockup-select').prop('checked', true);
      } else {
          $('.mockup-select').prop('checked', false);
      }
    });
});
