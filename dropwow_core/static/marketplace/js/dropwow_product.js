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
            $('#product-price').text('$' + current.price);
        }
    }

    // $('.dropwow-product-option').change(function() {
    //     showCombination();
    // });

    // showCombination();
})();