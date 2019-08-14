$(function() {
    $('#created_at_daterange').daterangepicker({
        format: 'MM/DD/YYYY',
        showDropdowns: true,
        showWeekNumbers: true,
        timePicker: false,
        autoUpdateInput: false,
        ranges: {
            'Today': [moment(), moment()],
            'Yesterday': [moment().subtract(1, 'days'), moment().subtract(1, 'days')],
            'Last 7 Days': [moment().subtract(6, 'days'), moment()],
            'Last 30 Days': [moment().subtract(29, 'days'), moment()],
            'This Month': [moment().startOf('month'), moment().endOf('month')],
            'Last Month': [moment().subtract(1, 'month').startOf('month'), moment().subtract(1, 'month').endOf('month')],
            'All Time': 'all-time',
        },
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
            daysOfWeek: ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'],
            monthNames: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
            firstDay: 1
        }
    }, function(start, end, label) {
        $('#created_at_daterange span').html(start.format('MMMM D, YYYY') + ' - ' + end.format('MMMM D, YYYY'));
        $('input[name="created_at_daterange"]').val(start.format('MM/DD/YYYY') + '-' + end.format('MM/DD/YYYY'));
    });

    $('#created_at_daterange').on('apply.daterangepicker', function(ev, picker) {
        var start = picker.startDate,
            end = picker.endDate;

        if (start.isValid && !end.isValid()) {
            end = moment();
        }

        if (start.isValid() && end.isValid()) {
            $('#created_at_daterange span').html(
                start.format(start.year() == moment().year() ? 'MMMM D' : 'MMMM D, YYYY') + ' - ' +
                end.format(end.year() == moment().year() ? 'MMMM D' : 'MMMM D, YYYY'));
            $('input[name="created_at_daterange"]').val(start.format('MM/DD/YYYY') + '-' + end.format('MM/DD/YYYY'));
        } else {
            $('#created_at_daterange span').html('All Time');
            $('input[name="created_at_daterange"]').val('all');
        }

        $('#search-form').submit();
    });

    $('#created_at_daterange').on('cancel.daterangepicker', function(ev, picker) {
        $('#created_at_daterange span').html('');
        $('input[name="created_at_daterange"]').val('');
    });

    var createdAtDaterangeValue = $('input[name="created_at_daterange"]').val();
    if (createdAtDaterangeValue && createdAtDaterangeValue.indexOf('-') !== -1) {
        var dates = createdAtDaterangeValue.split('-'),
            createdAtStart = moment(dates[0], 'MM/DD/YYYY'),
            createdAtEnd = moment(dates[1], 'MM/DD/YYYY');

        if (createdAtStart.isValid && !createdAtEnd.isValid()) {
            createdAtEnd = moment();
        }

        $('#created_at_daterange span').html(
            createdAtStart.format(createdAtStart.year() == moment().year() ? 'MMMM D' : 'MMMM D, YYYY') + ' - ' +
            createdAtEnd.format(createdAtEnd.year() == moment().year() ? 'MMMM D' : 'MMMM D, YYYY'));
    }

    $('body').on('click','.log-edit', function(e){
        var log_id = $(this).attr('data-log-id');
        var note = $('.note-text.log-id-' + log_id).html();
        var post_url = $(this).attr('data-post-url');

        $('#log-form-edit #log-note').val(note);
        $('#log-form-edit #log-id').val(log_id);
        $('#log-form-edit #post-url').val(post_url);
    });

    $('.update-log').click(function(e) {
        var note = $('#log-form-edit #log-note').val();
        var log_id = $('#log-form-edit #log-id').val();
        var post_url = $('#log-form-edit #post-url').val();

        $.ajax({
            url: post_url,
            type: 'POST',
            data: {
                'log_id': log_id,
                'note': note
            },
            context: {
                btn: this,
                parent: parent
            },
            success: function(data) {
                if (data.status == 'ok') {
                    toastr.success('Note', 'Note saved');

                    $('.note-text.log-id-' + log_id).html(note);
                } else {
                    displayAjaxError('Add Note', data);
                }
            },
            error: function(data) {
                displayAjaxError('Add Note', data);
            },
            complete: function() {
                $(this.btn).button('reset');
                $('.update-log-cancel').trigger('click');
            }
        });
    });

    $('#company_id,#created_at_daterange2').change(function(e) {
        $('#search-form').submit();
    });

    $('.table').on('click', '.delete-log', function(e) {
        console.log('click');
        e.preventDefault();

        var deleteLogURL = $(this).data('post-url');
        var deleteLogID = $(this).data('log-id');
        swal({
            title: 'Delete Log',
            text: 'Do you want to delete this log?',
            type: 'warning',
            html: true,
            animation: false,
            showCancelButton: true,
            confirmButtonColor: "#DD6B55",
            confirmButtonText: "Delete",
            cancelButtonText: "Cancel",
            closeOnCancel: true,
            closeOnConfirm: false,
            showLoaderOnConfirm: true,
        },
        function(isConfirmed) {
            if (!isConfirmed) {
                return;
            }

            $.ajax({
                url: deleteLogURL,
                type: 'POST',
                data: {
                    id: deleteLogID,
                },
                success: function(data) {
                    if (data.status == 'ok') {
                        $('#callflex-logs .callflex-log-' + data.id).hide('slow', function() {
                            $(this).remove();
                        });

                        swal.close();
                        toastr.success('Log have been deleted', 'Delete Log');
                    }
                },
                error: function(data) {
                    displayAjaxError('Delete Log', data);
                }
            });
        });
    });
});
