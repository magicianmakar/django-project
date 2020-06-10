$('.delete-custom-product-btn').click(function(e) {
    e.preventDefault();
    var btn = $(this);
    var product = btn.data('id');

    swal({
        title: "Delete Saved Product",
        text: "This will remove the product permanently. Are you sure you want to remove this product?",
        type: "warning",
        showCancelButton: true,
        closeOnConfirm: false,
        showLoaderOnConfirm: true,
        confirmButtonColor: "#DD6B55",
        confirmButtonText: "Remove Permanently",
        cancelButtonText: "Cancel"
    }, function(isConfirmed) {
        if (isConfirmed) {
            $.ajax({
                url: api_url('custom-product', 'prints') + '?' + $.param({id: product}),
                type: 'DELETE',
                success: function(data) {
                    btn.parents('.col-md-3').remove();

                    swal.close();
                    toastr.success("The product has been deleted.", "Deleted!");
                },
                error: function(data) {
                    displayAjaxError('Delete Saved Product', data);
                }
            });
        }
    });
});
