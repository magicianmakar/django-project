$(document).ready(function(){
    $('.custom-file-input').on('change', function() {
        var fileName = $(this).val().split('\\').pop();
        $(this).next('.custom-file-label').addClass("selected").html(fileName);
    });

    $("input[type='reset']").closest('form').on('reset', function() {
        $('.custom-file-label').each(function (i, el) {
            $(el).html($(el).data('placeholder'));
        });
    });

    $(".pls-reset-btn").click(function () {
        $(".form-control").each(function (i, item) {
            $(item).val('');
        });
    });
});
