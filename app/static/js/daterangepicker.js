function setupDateRangePicker(elment_id, input_id, useAllTime) {
    var dateRanges = {
        'Today': [moment(), moment()],
        'Yesterday': [moment().subtract(1, 'days'), moment().subtract(1, 'days')],
        'Last 7 Days': [moment().subtract(6, 'days'), moment()],
        'Last 30 Days': [moment().subtract(30, 'days'), moment()],
        'This Month': [moment().startOf('month'), moment().endOf('month')],
    };

    if (useAllTime) {
        dateRanges['All Time'] = 'all-time';
    }
    $(elment_id).daterangepicker({
        format: 'MM/DD/YYYY',
        minDate: moment().subtract(30 * 24, 'days'),
        showDropdowns: true,
        showWeekNumbers: true,
        timePicker: false,
        autoUpdateInput: false,
        ranges: dateRanges,
        opens: 'right',
        drops: 'down',
        buttonClasses: ['btn', 'btn-sm'],
        applyClass: 'btn-primary',
        cancelClass: 'btn-default',
        separator: ' to ',
        locale: {
            applyLabel: 'Submit',
            cancelLabel: 'Clear',
            fromLabel: 'From',
            toLabel: 'To',
            customRangeLabel: 'Custom Range',
            daysOfWeek: ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr','Sa'],
            monthNames: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
            firstDay: 1
        }
    }, function(start, end, label) {  // Callback
        if (start.isValid() && end.isValid()) {
            $(elment_id).find('span').html(start.format('MMMM D, YYYY') + ' - ' + end.format('MMMM D, YYYY'));
            $(input_id).val(start.format('MM/DD/YYYY') + '-' + end.format('MM/DD/YYYY'));
        }
    });

    $(elment_id).on('apply.daterangepicker', function(ev, picker) {
        var start = picker.startDate,
            end = picker.endDate;

        if (start.isValid && !end.isValid()) {
            end = moment();
        }

        if (start.isValid() && end.isValid()) {
            $(elment_id).find('span').html(
                start.format(start.year() == moment().year() ? 'MMMM D' : 'MMMM D, YYYY') + ' - ' +
                 end.format(end.year() == moment().year() ? 'MMMM D' : 'MMMM D, YYYY'));
            $(input_id).val(start.format('MM/DD/YYYY') + '-' + end.format('MM/DD/YYYY'));
        } else {
            $('#created_at_daterange span').html('All Time');
            $('input[name="created_at_daterange"]').val('all');
        }

        $(input_id).trigger('change');
    });

    $(elment_id).on('cancel.daterangepicker', function(ev, picker) {
        $(elment_id).find('span').html('');
        $(input_id).val('');
        $(input_id).trigger('change');
    });

    var createdAtDaterangeValue = $(input_id).val();
    if (createdAtDaterangeValue && createdAtDaterangeValue.indexOf('-') !== -1) {
        var dates = createdAtDaterangeValue.split('-'),
            createdAtStart = moment(dates[0], 'MM/DD/YYYY'),
            createdAtEnd = moment(dates[1], 'MM/DD/YYYY');

        if (createdAtStart.isValid && !createdAtEnd.isValid()) {
            createdAtEnd = moment();
        }

        $(elment_id).find('span').html(
            createdAtStart.format(createdAtStart.year() == moment().year() ? 'MMMM D' : 'MMMM D, YYYY') + ' - ' +
            createdAtEnd.format(createdAtEnd.year() == moment().year() ? 'MMMM D' : 'MMMM D, YYYY'));
    }
}
