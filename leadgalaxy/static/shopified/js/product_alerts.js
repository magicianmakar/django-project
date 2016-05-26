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