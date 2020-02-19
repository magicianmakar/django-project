$(document).ready(function(){
    $('.product-images').slick({
        dots: true
    });

    $('#user_supplement_form input[type=submit]').click(function() {
        var action = $(this).data('action');
        document.user_supplement_form.action.value = action;
    });
});
