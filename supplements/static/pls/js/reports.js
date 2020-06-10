$(document).ready(function() {
    $("#id_start_date,#id_end_date").datepicker();

    $('#config-type').change(function(e) {
        $('.config-block').css('display', 'none');
        $($('#config-type').val()).css('display', 'block');
        $('.config-block select').each(function(i, el) {
            $(el).val('');
        });
        $('.config-block input').each(function(i, el) {
            $(el).val('');
        });
    });

    $('.config-block select').change(function(e) {
        var el_id = $(e.target).attr('id');
        $('.config-block select').each(function(i, el) {
            if (el_id != $(el).attr('id')) {
                $(el).val('');
            }
        });
        $('.config-block input').each(function(i, el) {
            if (el_id != $(el).attr('id')) {
                $(el).val('');
            }
        });
    });

    $('.config-block input').change(function(e) {
        $('.config-block select').each(function(i, el) {
            if (el_id != $(el).attr('id')) {
                $(el).val('');
            }
        });
    });

    $('.reports-reset-btn').click(function() {
        $('.config-block').css('display', 'none');
        $('#config-period-block').css('display', 'block');
        $('select[name="report-type"]').val('#config-period-block');
        $('select[name="period"]').val('week');
        $('select[name="interval"]').val('day');
        $('select[name="compare"]').val('');
        $('.config-block input').each(function(i, el) {
            $(el).val('');
        });
    });

});