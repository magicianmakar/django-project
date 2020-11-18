
$(document).ready(function(){


    $(".pls-add-basket").click(function (e) {
        e.preventDefault();
        var product_id=$(this).data('product-id');

        var data = {'product-id': product_id};

        var url = api_url('add_basket', 'supplements');
        $.ajax({
            url: url,
            type: "POST",
            data: JSON.stringify(data),
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
               toastr.success("Item added to your <a href='#'>Basket</a>");
            },
            error:
            function (response) {
               toastr.error("Error adding item to your <a href='#'>Basket</a>");
            },
        });
    });



    $(".basket-row .basket-item-quantity").change(function (e) {
        e.preventDefault();
        var basket_id=$(this).data('basket-id');
        var quantity=$(this).val();

        var data = {'basket-id': basket_id, 'quantity': quantity};

        var url = api_url('update_basket', 'supplements');
        $.ajax({
            url: url,
            type: "POST",
            data: JSON.stringify(data),
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
               toastr.success("Item quantity updated");
               if (response.quantity==0){
                   $(".basket-id-"+basket_id).remove();
               }
               else {
                   $(".basket-id-"+basket_id+" .basket-item-total-price").html(response.total_price);
               }
               basket_update_totals();
            },
            error:
            function (response) {
               toastr.error("Error updating item");
            },
        });
    });

    $(".basket-row .basket-item-remove").click(function (e) {

        $(this).parents('.basket-row').find('.basket-item-quantity').val(0);
        $(this).parents('.basket-row').find('.basket-item-quantity').trigger('change');

    });

    $('.basket-total').each(function(){
        basket_update_totals();

    });


    function basket_update_totals(){
         var url = api_url('basket_total', 'supplements');
        $.ajax({
            url: url,
            type: "GET",
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                $('.basket-total').html(response.total);
                if (response.total<=0) {
                    window.location.reload();
                }
            },
            error:
            function (response) {
               toastr.error("Error updating item");
            },
        });
    }

});
