$(document).ready(function(){
    $('.product-images').slick({
        dots: true
    });

    $('#user_supplement_form input[type=submit]').click(function() {
        document.user_supplement_form.action.value = $(this).data('action');
    });
});
