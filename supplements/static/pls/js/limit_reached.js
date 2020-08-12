$('.limit-reached').on('click', function(e) {
    if (limitReached) {
        e.preventDefault();
        $('#limit-reached-modal').modal('show');

        if ($('[name="current_label"]').val()) {
            $('#limit-reached-modal .existing-label').removeClass('hidden');
        } else {
            $('#limit-reached-modal .existing-label').addClass('hidden');
        }
    }
});
