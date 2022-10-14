(function() {
    'use strict';

    $('.product-review').on('click', function(e) {
        e.preventDefault();
        $('#product-review-modal').modal('show');
        setRatingTab(this);
        setCommentsTab(this);
    });

    function setStarRatings(stars, avg_rating){
        $(stars).each(function(){
            $(this).removeAttr('style');
            var rating = parseFloat($(this).attr("rating"));
            if(rating <= avg_rating){
                $(this).css('color','#FABF35');
            } else if (rating == parseInt(avg_rating + 1)){
                var per = (avg_rating + 1 - rating) * 100;
                var gradient = 'linear-gradient(to right, #FABF35 '+per+'%, #E8E8E8 0%)';
                $(this).css('background-image', gradient);
                $(this).addClass('multi-color');
            } else {
                $(this).css('color','#E8E8E8');
            }
        });
    }

    function setRatingTab(product_rating){
        var avg_rating = parseFloat($(product_rating).attr('avg-rating'));
        $('#product-review-modal #avg_rating').text(avg_rating);
        $('#product-review-modal #count').text($(product_rating).attr('count'));
        $('#review-product-quality div').css("width",$(product_rating).attr('pq-rating')+"%");
        $('#review-product-quality div').attr("aria-valuenow",$(product_rating).attr('pq-rating'));
        $('#review-label-quality div').css("width",$(product_rating).attr('lq-rating')+"%");
        $('#review-label-quality div').attr("aria-valuenow",$(product_rating).attr('lq-rating'));
        $('#review-delivery div').css("width",$(product_rating).attr('dl-rating')+"%");
        $('#review-delivery div').attr("aria-valuenow",$(product_rating).attr('dl-rating'));
        var stars = $('.product-rating-star');
        setStarRatings(stars, avg_rating);
    }

    function setCommentsTab(item){
        var supplement_reviews = JSON.parse($(item).attr('reviews'));
        $('#product-review-modal #comment_count').text(supplement_reviews.length);
        populateCommentsTemplate(supplement_reviews);
    }

    function populateCommentsTemplate(reviews){
        $('#comment-list div').remove();
        for (var index = 0; index < reviews.length; index++) {
            var element = reviews[index];
            $('#comment-template #first_name').text(element['user__first_name']);
            $('#comment-template #last_name').text(element['user__last_name']);
            $('#comment-template #comment').text(element['comment']);
            var stars =  $('#comment-template .product-rating-star-user');
            var avg_rating = parseFloat(
                (element['product_quality_rating'] + element['label_quality_rating'] + element['delivery_rating']) / 3
            );
            setStarRatings(stars, avg_rating);
            $('#comment-list').append($('#comment-template').html());
        }
    }

    $("#supplier_profile").click(function() {
        $('#modal-supplier_profile').modal({backdrop: 'static', keyboard: false});
        if($(this).attr('reviews') != '') {
            var supplier_reviews = JSON.parse($(this).attr('reviews'));
            $('#modal-supplier_profile #comment_count').text(supplier_reviews.length);
            populateCommentsTemplate(supplier_reviews);
        }else {
            $('#modal-supplier_profile #comment_count').text('0');
        }
    });
})();
