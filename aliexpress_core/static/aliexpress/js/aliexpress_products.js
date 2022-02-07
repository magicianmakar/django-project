/* global $, toastr, swal, displayAjaxError */

function getStars(rating) {
    // Round to nearest half
    rating = Math.round(rating * 2) / 2;
    var output = [];
    var i, j;

    // Append all the filled whole stars
    for (i = rating; i >= 1; i--) {
        output.push('<i class="fa fa-star"></i>&nbsp;');
    }

    // If there is a half a star, append it
    if (i == 0.5) {
        output.push('<i class="fa fa-star-half-o"></i>&nbsp;');
    }

    // Fill the empty stars
    for (j = (5 - rating); j >= 1; j--) {
        output.push('<i class="fa fa-star-o"></i>&nbsp;');
    }

    return output.join('');
}

$(document).ready(function() {
    $('.card-reviews').each(function() {
        var ratingPercent = $(this).data('rating');
        var rating = Number((Number(ratingPercent) / 20).toFixed(1));
        $(this).html(getStars(rating));
    });

    $('.aliexpress-import-by-url').on('click', function(e) {
        var inputData = $('#aliexpress_product_url').val();
        if (!inputData) {
            toastr.info("Please add an AliExpress product URL or ID.");
            return;
        }
        $('#modal-aliexpress-import-by-url').modal('hide');
        var matches = inputData.match(/.*?(\d+)(?:$|.html)/);
        $('#aliexpress_product_id').val(matches[1]);
        $('#modal-aliexpress-import-products').modal('show');
        $('#aliexpress_product_url').val('');
    });

    $('.aliexpress-import-btn').on('click', function(e) {
        $('#aliexpress_product_id').val($(this).data('product-id'));
    });

    $('.aliexpress-save-btn').on('click', function(e) {
        e.preventDefault();
        var btn = $(this);
        btn.button('loading');

        var data = {
            'product_id': $('#aliexpress_product_id').val(),
            'currency': $('#aliexpress_product_currency').val(),
            'publish': $(this).data('publish'),
            'store_ids': [],
        };
        $(".aliexpress-store-select").each(function (i, item) {
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
            url: api_url('import-aliexpress-product', 'aliexpress'),
            type: "POST",
            data: JSON.stringify(data),
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                btn.button('reset');
                $('#modal-aliexpress-import-products').modal('hide');
                toastr.success('The product has been saved.', 'Product Import');
            },
            error: function (response) {
                btn.button('reset');
                $('#modal-aliexpress-import-products').modal('hide');
                displayAjaxError('Product Import', response);
            },
        });
    });
});
