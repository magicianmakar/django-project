/* global $, toastr, swal, displayAjaxError */

$(document).ready(function() {
    $('.alibaba-import-btn').on('click', function(e) {
        $('#alibaba_product_id').val($(this).data('product-id'));
    });

    $('.alibaba-import-by-url').on('click', function(e) {
        var inputData = $('#alibaba_product_url').val();
        if (!inputData) {
            toastr.info("Please add an Alibaba product URL or ID.");
            return;
        }
        $('#modal-alibaba-import-by-url').modal('hide');
        var matches = inputData.match(/.*?(\d+)(?:$|.html)/);
        $('#alibaba_product_id').val(matches[1]);
        $('#modal-alibaba-import-products').modal('show');
        $('#aliexpress_product_url').val('');
    });

    $('.alibaba-save-btn').on('click', function(e) {
        e.preventDefault();
        var btn = $(this);
        btn.button('loading');

        var data = {
            'pid': $('#alibaba_product_id').val(),
            'publish': $(this).data('publish'),
            'store_ids': [],
        };

        $(".alibaba-store-select").each(function (i, item) {
            var value = $(item).val();
            if ($(item).prop('checked')) {
                data['store_ids'].push(value);
            }
        });
        if (data['store_ids'].length == 0) {
            toastr.info("Please select at least one store to add products.");
            btn.button('reset');
            return;
        }

        $.ajax({
            url: api_url('import-alibaba-product', 'alibaba'),
            type: "POST",
            data: JSON.stringify(data),
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                btn.button('reset');
                $('#modal-alibaba-import-products').modal('hide');
                toastr.success('The product has been saved.', 'Product Import');
            },
            error: function (response) {
                btn.button('reset');
                $('#modal-alibaba-import-products').modal('hide');
                displayAjaxError('Product Import', response);
            },
        });
    });
});
