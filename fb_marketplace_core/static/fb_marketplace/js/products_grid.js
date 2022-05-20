/* global $, toastr, swal, displayAjaxError, sendProductToShopify */
/* global sendProductToEbay, api_url, Pusher */

(function() {
'use strict';

$('.bulk-action').on('click', function(e) {
    var action = $(this).attr('data-bulk-action');

    if (action.length === 0) {
        if ($(this).hasClass('not-connected')) {
            window.location.href = $(this).attr('href');
            return;
        }
        swal('Please select an action first', '', "warning");
        return;
    }

    if (action === 'delete') {
        swal({
                title: "Delete Selected Products",
                text: "This will remove the selected products permanently. Are you sure you want to remove those products?",
                type: "warning",
                showCancelButton: true,
                confirmButtonColor: "#DD6B55",
                confirmButtonText: "Remove Permanently",
                cancelButtonText: "Cancel"
            },
            function(isConfirmed) {
                if (isConfirmed) {
                    $('input.item-select[type=checkbox]').each(function(i, el) {
                        if (el.checked) {
                            var node = $(el);
                            var productId = node.parents('.product-box').attr('product-id');
                            deleteProduct(productId, function() {
                                node.parents('.col-md-3').remove();
                            });
                            node.iCheck('uncheck');
                        }
                    });
                }
            });
    }

    $('#selected-actions').val('');
    $('input.item-select[type=checkbox]').each(function(i, el) {
        if (el.checked) {
            var product = $(el).parents('.product-box').attr('product-id');

            if (action != 'delete') {
                $(el).iCheck('uncheck');
            }
        }
    });
});

function deleteProduct(productGuid, callback) {
    $.ajax({
        url: api_url('product', 'fb_marketplace') + '?' + $.param({product: productGuid}),
        type: 'DELETE',
        success: function(data) {
            callback(data);
        },
        error: function(data) {
            displayAjaxError('Delete Product', data);
        }
    });
}

})();
