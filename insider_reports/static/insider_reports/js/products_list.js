(function () {



    $('.import-alibaba-product-btn').click(function(){
        var alibabaProductId = $(this).parents('.alibaba-product').data('alibabaProductId');
        var alibabaAccountId = $(this).parents('.alibaba-products').data('alibabaAccountId');
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



    $('.import-alibaba-products-btn').click(function(){
        $('.import-alibaba-products:checked').each(function(){
           $(this).parents('.alibaba-product').find('.import-alibaba-product-btn').click();
        });


    });


    $('.import-alibaba-products').change(function(){

        if(this.checked){
            $(this).parents('.alibaba-product').addClass('selected');
        }
        else {
            $(this).parents('.alibaba-product').removeClass('selected');
        }

        update_bar();
    });

    function update_bar(){
        if ($('.import-alibaba-products:checked').length >0 ) {
            $('.bulk-bar').show('slide', { direction: "down" }, 500);
        }
        else {
            $('.bulk-bar').hide('slide', { direction: "down" }, 500);
        }

        $('.total-selected').html($('.import-alibaba-products:checked').length);

    }

    $('#top-search-form').submit(function(e){
        e.preventDefault();
        $('#filter-keyword').val( $('#top-search').val() );
        $('#filter-form').submit();
        return false;

    });

    $('.changepage a').click(function(e){
        e.preventDefault();
        $('#filter-page').val( $(this).data('page') );
        $('#filter-form').submit();
        return false;

    });

    $('#cat_id').change(function(e){

       //update_filtertags();

    });


    function update_filtertags(){

        $('#filtertags').hide();


        $('.filter-cat').remove();
        if ($('#cat_id').val()!='' ) {
            $('#filtertags').show();
            $('#filtertags').append('<span class="btn-sm btn-warning tag-item filter-cat" data-cat-id="'+$('#cat_id').val()+'">'+$('#cat_id option:selected').html()+' <a href="#" class="remove-cat remove-tag-btn"><i class="fa fa-times"></i></a></span>');
        }




    }


    // update_filtertags();

    $('#cat_id').multiselect({
        includeSelectAllOption: true,
        nonSelectedText: 'Categories',
        buttonClass: 'btn btn-link',
        selectAllText: 'All Categories',
        selectAllValue: '1',
        selectAllName: 'cat_id_all'
    });



}());
