/* global $, api_url, displayAjaxError, swal, toastr, sendProductToGoogle, Pusher */

$(document).ready(function() {
    'use strict';

    $('.google-shop-box').on('click', function() {
        var shopBox = $(this);
        var authorizeButton = $('#authorize-google-shop-button');

        var cmsId = shopBox.data('cms-id');
        var shopName = shopBox.data('shop-name');

        var authButtonStrings = ['Authorize'];
        if (shopName) {
            authButtonStrings.push(shopName);
        }

        $('#google-shops-container .google-shop-box').each(function(i, shopEl) {
            $(shopEl).removeClass('google-shop-box--selected');
        });
        shopBox.addClass('google-shop-box--selected');
        authorizeButton.text(authButtonStrings.join(' '));
        $('#selected-google-cms-id').val(cmsId);
    });

    $('#authorize-google-shop-form').on('submit', function(e) {
        e.preventDefault();
        var btn = $('#authorize-google-shop-button');
        var continueWithGoogleButton = $('#google-store-create-submit-btn');
        var data = $(this).serialize();

        btn.bootstrapBtn('loading');
        continueWithGoogleButton.bootstrapBtn('loading');

        $.ajax({
            url: api_url('onboard-store', 'google'),
            type: 'POST',
            data: data,
            context: {btn: btn, continueWithGoogleButton: continueWithGoogleButton},
            success: function(data) {
                this.btn.bootstrapBtn('reset');
                this.continueWithGoogleButton.bootstrapBtn('reset');
                toastr.success('The store has been successfully onboarded.', 'Store Onboarded!');
                setTimeout(function() { window.location.href = '/google'; }, 500);
            },
            error: function (data) {
                this.btn.bootstrapBtn('reset');
                this.continueWithGoogleButton.bootstrapBtn('reset');
                displayAjaxError('Onboard Google Store', data);
            }
        });
    });

    (function() {
        var firstShop = $('#google-shops-container .google-shop-box').first();

        var cmsId = firstShop.data('cms-id');
        var shopName = firstShop.data('shop-name');

        var authButtonStrings = ['Authorize'];
        if (shopName) {
            authButtonStrings.push(shopName);
        }

        firstShop.addClass('google-shop-box--selected');
        $('#authorize-google-shop-button').text(authButtonStrings.join(' '));
        $('#selected-google-cms-id').val(cmsId);
    })();
});
