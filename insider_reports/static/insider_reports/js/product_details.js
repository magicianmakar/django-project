(function () {


    $('.details-import-alibaba-product-btn').click(function(){
        var alibabaProductId = $(this).data('alibabaProductId');
        var alibabaAccountId = $(this).data('alibabaAccountId');

        if (!alibabaAccountId) {
            toastr.error('You need to Authorize your Alibaba Account on Setting page','Product Import Error');
            return(false);
        }
        var button = $(this);
        $(this).html('Adding...');
        button.removeClass('btn-danger');
        button.removeClass('btn-primary');
        button.addClass('btn-info');
        $.ajax({
                    type: 'GET',
                    url: '/webhook/alibaba/add-product?user_id='+alibabaAccountId+'&id='+alibabaProductId,
                    success: function (data) {
                        button.html('Imported');
                        button.removeClass('btn-danger');
                        button.removeClass('btn-info');
                        button.addClass('btn-primary');

                        button.parents('.alibaba-product').find('.import-alibaba-products').prop('checked', false);
                        button.parents('.alibaba-product').find('.import-alibaba-products').change();
                        update_bar();
                    },
                    error: function (data) {
                        button.html('Error');
                        button.removeClass('btn-primary');
                        button.removeClass('btn-info');
                        button.addClass('btn-danger');

                    }
                });

    });


    $('.extra-image').click(function(){
        $('.product-large-image').prop('src',$(this).data('imagelarge') );


    });


    $('.product-description img').each(function(){

        if ($(this).data('src')) {
            $(this).prop('src', $(this).data('src'));
        }
    });


      // Gets the span width of the filled-ratings span
      // this will be the same for each rating
      var star_rating_width = $('.fill-ratings span').width();
      // Sets the container of the ratings to span width
      // thus the percentages in mobile will never be wrong
      $('.star-ratings').width(star_rating_width);


      $('.images-carousel').slick({
          infinite: true,
          // the magic
          slidesToShow: 5,
          slidesToScroll: 5,
          responsive: [
            {
              breakpoint: 1600,
              settings: {
                slidesToShow: 4,
                slidesToScroll: 4,
                infinite: true,
                dots: true
              }
            },
            {
              breakpoint: 1400,
              settings: {
                slidesToShow: 3,
                slidesToScroll: 3,
                infinite: true,
                dots: true
              }
            },
            {
              breakpoint: 1200,
              settings: {
                slidesToShow: 2,
                slidesToScroll: 2
              }
            },
            {
              breakpoint: 480,
              settings: {
                slidesToShow: 1,
                slidesToScroll: 1
              }
            }
            // You can unslick at a given breakpoint now by adding:
            // settings: "unslick"
            // instead of a settings object
          ]
        });


}());
