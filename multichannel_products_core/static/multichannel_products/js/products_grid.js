/* global $, toastr, swal, displayAjaxError, sendProductToShopify */
/* global api_url, Pusher */

$(function() {
    'use strict';
    $('.bulk-action').on('click', function(e) {
    e.preventDefault();
    var action = $(this).attr('data-bulk-action');

    if (!$('input.item-select[type=checkbox]').is(':checked')) {
        if ($(this).hasClass('not-connected')) {
            window.location.href = $(this).attr('href');
            return;
        }
        swal('Please select a product first', '', "warning");
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
                            var product = $(el).parents('.product-box').attr('product-id');
                            $.ajax({
                                url: api_url('product', 'multichannel') + '?' + $.param({product: product}),
                                type: 'DELETE',
                                success: function(data) {
                                    $(el).parents('.col-md-3').remove();
                                },
                                error: function(data) {
                                    swal("Error", "Server Error", "error");
                                }
                            });

                            $(el).iCheck('uncheck');
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
});
