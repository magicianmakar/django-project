/* global $, toastr, swal, displayAjaxError, sendProductToShopify */
/* global boardsMenu */

(function() {
    'use strict';
    $('.view-details, .details-toggle').click(function(e) {
        e.preventDefault();

        $(this).parents('tr').next('.details').toggle('fast');
    });

    $('.archive-alert').click(function(e) {
        e.preventDefault();

        $.ajax({
            url: '/api/alert-archive',
            type: 'POST',
            data: {
                'alert': $(this).attr('alert-id')
            },
            context: {
                alert: $(this).attr('alert-id')
            },
            success: function(data) {
                $('tr[alert-id="' + this.alert + '"]').hide('slide');
            },
            error: function(data) {
                displayAjaxError('Archive Alert', data);
            }
        });
    });

    $('#archive-all-alerts').click(function(e) {
        e.preventDefault();
        var storeId = $(this).attr('store-id');

        swal({
            title: "Archive Alerts",
            text: "Are you sure you want to archive all Alerts?",
            type: "warning",
            showCancelButton: true,
            closeOnCancel: true,
            closeOnConfirm: false,
            confirmButtonColor: "#DD6B55",
            confirmButtonText: "Archive All",
            cancelButtonText: "Cancel"
        },
        function(isConfirmed) {
            if (isConfirmed) {
                $.ajax({
                    url: '/api/alert-archive',
                    type: 'POST',
                    data: {
                        'all': '1',
                        'store': storeId
                    },
                    success: function(data) {
                        setTimeout(function() {
                            window.location.reload();
                        }, 1000);

                        swal.close();
                        toastr.success('Alerts have been Archived', 'Archive Alerts');
                    },
                    error: function(data) {
                        displayAjaxError('Archive Alerts', data);
                    }
                });
            }
        });
    });

    $('#delete-all-alerts').click(function(e) {
        e.preventDefault();
        var storeId = $(this).attr('store-id');

        swal({
            title: "Delete Alerts",
            text: "Are you sure you want to permanently delete all Alerts?",
            type: "warning",
            showCancelButton: true,
            closeOnCancel: true,
            closeOnConfirm: false,
            confirmButtonColor: "#DD6B55",
            confirmButtonText: "Delete Permanently",
            cancelButtonText: "Cancel"
        },
        function(isConfirmed) {
            if (isConfirmed) {
                $.ajax({
                    url: '/api/alert-delete',
                    type: 'POST',
                    data: {
                        'all': '1',
                        'store': storeId
                    },
                    success: function(data) {
                        setTimeout(function() {
                            window.location.reload();
                        }, 1000);

                        swal.close();
                        toastr.success('Alerts have been deleted', 'Delete Alerts');
                    },
                    error: function(data) {
                        displayAjaxError('Delete Alerts', data);
                    }
                });
            }
        });
    });

    $('.open-orders-btn').click(function (e) {
        e.preventDefault();

        window.open('/orders?' + $.param({
            product: $(this).data('product'),
            status: $(this).data('orders') ? 'open' : 'any',
            fulfillment: $(this).data('orders') ? 'unshipped' : 'any',
            financial: $(this).data('orders') ? 'paid' : 'any',
        }), 'SA_Order');
    });

    $.contextMenu({
        selector: '.open-product-in',
        trigger: 'left',
        callback: function(key, options) {
            if (key == 'shopify') {
                var url = options.$trigger.attr('shopify-link');
                if (url && url.length) {
                    window.open(url, '_blank');
                } else {
                    toastr.warning('Product is not connected');
                }

            } else if (key == 'original') {
                window.open(options.$trigger.attr('original-link'), '_blank');
            } else if (key == 'shopified') {
                window.open('/product/' + options.$trigger.attr('product-id'), '_blank');
            }
        },
        items: {
            "original": {
                name: 'Original Product'
            },
            "shopify": {
                name: 'Shopify'
            },
            "shopified": {
                name: 'Shopified App'
            },
        },
        events: {
            show: function(opt) {
                setTimeout(function() {
                    opt.$menu.css({
                        'z-index': '10000',
                        'max-height': '300px',
                        'overflow': 'auto',
                    });
                }, 100);

                return true;
            }
        }
    });
    $(function() {
        $('.view-details').trigger('click').hide('fast');
    });
})();