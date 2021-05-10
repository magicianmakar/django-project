$("#id_comment").attr("placeholder", "Leave a comment...");
$("input[name='is_private']").change(function() {
    $("#id_comment").toggleClass('bg-private', $(this).is(":checked"));
    if($(this).is(":checked")) {
        $("#id_comment").attr("placeholder", "Leave a private note...");
    } else {
        $("#id_comment").attr("placeholder", "Leave a comment...");
    }
});
