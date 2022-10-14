(function() {
    'use strict';

    function setActiveRatingColor(elements, click){
        $(elements).each(function(){
            if(click){
                $(this).parent().addClass("selected");
            }
            var rating = $(this).parent().attr("rating");
            if (rating <= 3) {
                $(this).parent().children().css('color','#FABF35');
            }
            else {
                $(this).parent().children().css('color','#BB8300');
                $(this).parent().children().first().css('color','#FABF35');
            }
        });
    }

    function setNormalRatingColor(elements, click){
        $(elements).each(function(){
            if(!$(this).parent().hasClass("selected") | click){
                $(this).parent().removeClass("selected");
                var rating = $(this).parent().attr("rating");
                if (rating <= 3) {
                    $(this).parent().children().css('color','#E8E8E8');
                } else {
                    $(this).parent().children().css('color','#C6C6C6');
                    $(this).parent().children().first().css('color','#E8E8E8');
                }
            }
        });
    }

    function setRatingColor(star, active, click){
        $(star).parent().parent().children().each(function(){
            var currentStar = $(this).children().last();
            if(active & $(this).attr("rating") <= $(star).parent().attr("rating")){
                setActiveRatingColor(currentStar, click);
            } else {
                setNormalRatingColor(currentStar, click);
            }
        });
    }

    $('.review-btn').click(function(e) {
        if ($(this).prop('reviewed')) {
            return;
        }
        $('#modal-review #review-order-id').val($(this).attr('order-id'));
        $('#modal-review #review-line-id').val($(this).attr('line-id'));
        $('#modal-review #review-product-id').val($(this).attr('product-id'));
        $('#modal-review #review-store').val($(this).attr('store'));
        $('#modal-review #product-quality-rating').val(5);
        $('#modal-review #label-quality-rating').val(5);
        $('#modal-review #delivery-rating').val(5);

        setActiveRatingColor($('.rating-star .path4'),$('.rating-star .path4'));

        $('#modal-review').modal('show');
    });

    $('.rating-star .path4').hover(
        function(e) {
            setRatingColor(this, true, false);
        },
        function(e) {
            setRatingColor(this, false, false);
        }
    );

    $('.rating-star .path4').click(
        function(e) {
            var rating = $(this).parent().attr("rating");
            var rating_id = "#"+$(this).parent().parent().attr("id").split("review-")[1]+"-rating";
            $(rating_id).val(rating);
            setRatingColor(this, false, true);
            setRatingColor(this, true, true);
        }
    );

    $('#review-order-btn').click(function(e) {
        e.preventDefault();
        $(this).button('loading');
        var line_btn = $('.review-btn[line-id="' + $('#modal-review #review-line-id').val() + '"]');
        $.ajax({
            url: api_url('review-order', 'product_common'),
            type: 'POST',
            data: $('#modal-review form').serialize(),
            context: {
                btn: $(this),
                line: line_btn
            },
            success: function(data) {
                if (data.status == 'ok') {
                    $('#modal-review').modal('hide');
                    this.line.prop('reviewed', true);
                    toastr.success('Review Status changed to Reviewed.', 'Review Status');
                } else {
                    displayAjaxError('Review Error', data);
                }
            },
            error: function(data) {
                displayAjaxError('Review Error', data);
            },
            complete: function() {
                this.btn.button('reset');

                var btn = this.line;
                setTimeout(function() {
                    if (btn.prop('reviewed')) {
                        btn.text('Reviewed');
                    }
                }, 100);
            }
        });
    });
})();
