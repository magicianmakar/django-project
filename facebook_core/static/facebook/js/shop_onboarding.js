/* global $, api_url, displayAjaxError, swal, toastr, sendProductToFB, Pusher */

$(document).ready(function() {
    'use strict';

    $('.fb-shop-box').on('click', function() {
        var shopBox = $(this);
        var authorizeButton = $('#authorize-fb-shop-button');

        var cmsId = shopBox.data('cms-id');
        var shopName = shopBox.data('shop-name');

        var authButtonStrings = ['Authorize'];
        if (shopName) {
            authButtonStrings.push(shopName);
        }

        $('#fb-shops-container .fb-shop-box').each(function(i, shopEl) {
            $(shopEl).removeClass('fb-shop-box--selected');
        });
        shopBox.addClass('fb-shop-box--selected');
        authorizeButton.text(authButtonStrings.join(' '));
        $('#selected-fb-cms-id').val(cmsId);
    });

    $('#authorize-fb-shop-form').on('submit', function(e) {
        e.preventDefault();
        var btn = $('#authorize-fb-shop-button');
        var continueWithFbButton = $('#fb-store-create-submit-btn');
        var data = $(this).serialize();

        btn.bootstrapBtn('loading');
        continueWithFbButton.bootstrapBtn('loading');

        $.ajax({
            url: api_url('onboard-store', 'fb'),
            type: 'POST',
            data: data,
            context: {btn: btn, continueWithFbButton: continueWithFbButton},
            success: function(data) {
                this.btn.bootstrapBtn('reset');
                this.continueWithFbButton.bootstrapBtn('reset');
                toastr.success('The store has been successfully onboarded.', 'Store Onboarded!');
                setTimeout(function() { window.location.href = '/fb'; }, 500);
            },
            error: function (data) {
                this.btn.bootstrapBtn('reset');
                this.continueWithFbButton.bootstrapBtn('reset');
                displayAjaxError('Onboard Facebook Store', data);
            }
        });
    });

    (function() {
        var firstShop = $('#fb-shops-container .fb-shop-box').first();

        var cmsId = firstShop.data('cms-id');
        var shopName = firstShop.data('shop-name');

        var authButtonStrings = ['Authorize'];
        if (shopName) {
            authButtonStrings.push(shopName);
        }

        firstShop.addClass('fb-shop-box--selected');
        $('#authorize-fb-shop-button').text(authButtonStrings.join(' '));
        $('#selected-fb-cms-id').val(cmsId);
    })();
});
