/* global $, toastr, swal, displayAjaxError, dropwow_products */

(function() {
    'use strict';
    $('#product-image').slick();
    function showCombination() {
        var dropwow_product = dropwow_products[0];
        var current;
        for (var i = 0; i < dropwow_product.combinations.length; i++) {
            var combination = dropwow_product.combinations[i].combination;
            var match = true;
            for (var option in combination) {
                if (combination.hasOwnProperty(option)) {
                    if ($('#option_' + option).val() != combination[option]) {
                        match = false;
                        break;
                    }
                }
            }
            if (match) {
                current = dropwow_product.combinations[i];
                break;
            }
        }
        if (current) {
            var modifier = 0;
            for (var option_id in current.combination) {
                if (current.combination.hasOwnProperty(option_id)) {
                    var option = dropwow_product.options[option_id];
                    for (var i = 0; i < option.variants.length; i++) {
                        if (current.combination[option_id] == option.variants[i].variant_id) {
                            modifier = modifier + option.variants[i].modifier - 1;
                        }
                    }
                }
            }
            var price = dropwow_product.price + modifier;
            price = Math.round(price * 100) / 100;
            $('#product-price').text('$' + price);
            $('#product-quantity').text(current.quantity);
        }
    }

    $('.dropwow-product-option').change(function() {
        showCombination();
    });

    showCombination();
})();