window.OrderExportFilter = {
    dateTypeSelect: $('.date-type'),
    datePicker: $('.datepicker input'),
    clockPicker: $('.clockpicker'),
    init: function() {
        this.datePicker.datepicker();
        $('.clockpicker').clockpicker();

        this.onDateTypeChange();
    },
    onDateTypeChange: function() {
        this.dateTypeSelect.on('change', function() {
            if ($(this).val() == 'exact-date') {
                if (['created_at_min_type', 'processed_at_min_type'].indexOf($(this).attr('name')) > -1 ) {
                    var select = $(this).parents('.form-group').next().find('select.date-type');
                    if (select.find('value="exact-date"').length == 0) {
                        select.find('option:first').after($('<option value="exact-date">').text('Exactly'));
                    }
                }
                $(this).parents('.form-group').find('.exact-date').removeClass('hidden');
                $(this).parents('.form-group').find('.days-ago').addClass('hidden');
            } else if ($(this).val() == 'days-ago') {
                if (['created_at_min_type', 'processed_at_min_type'].indexOf($(this).attr('name')) > -1 ) {
                    $(this).parents('.form-group').next().find('select.date-type').find('option[value="exact-date"]').remove().trigger('change');
                }
                $(this).parents('.form-group').find('.exact-date').addClass('hidden');
                $(this).parents('.form-group').find('.days-ago').removeClass('hidden');
            }
        });
    }
};

window.OrderExportFilter.init();