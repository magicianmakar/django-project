$(document).ready(function() {
    'use strict';

    $('.dataTables').on('draw.dt', function(e) {
        $('.dataTables tr').each(function(i, el) {
            var info = $(el).find('td');

            if (info.length == 1) {
                $(el).find('td').last().text('No board found.').addClass('text-center');
                return;
            }
        });
    });

    var table = $('.dataTables').dataTable({
        responsive: true,
        autoWidth: false,
        dom: 'T<"clear">lfrtip',
        bLengthChange: false,
        iDisplayLength: 25,
        tableTools: {
            aButtons: [],
        }
    });

    $('.chq-add-board-btn').click(function(e) {
        e.preventDefault();
        $('#chq-modal-board-add').modal('show');
    });

    $("#chq-new-board-add-form").ajaxForm({
        target: "#chq-new-board-add-form",
        clearForm: true,
        data: {csrfmiddlewaretoken: Cookies.get('csrftoken')},
        success: function(responseText, statusText, xhr, $form) {
            if (xhr.status == 201) {
                window.location.reload();
            }
        }
    });

    $('.chq-edit-board-btn').click(function(e) {
        e.preventDefault();
        var action = $(this).data('board-update-url');

        $('#chq-board-update-form').prop('action', action);

        $.get(action)
            .done(function(data) {
                $('#chq-board-update-form').html(data);
                $('#chq-modal-board-update').modal('show');
            })
            .fail(function(jqXHR) {
                if (jqXHR.status == 401) {
                    window.location.reload();
                }
            });
    });

    $('#chq-board-update-form').ajaxForm({
        target: '#chq-board-update-form',
        clearForm: true,
        data: {csrfmiddlewaretoken: Cookies.get('csrftoken')},
        success: function(responseText, statusText, xhr, $form) {
            if (xhr.status == 204) {
                window.location.reload();
            }
        }
    });

    $('.chq-delete-board-btn').click(function(e) {
        e.preventDefault();
        var boardId = $(this).data('board-id');
        var action = $(this).data('board-delete-url');

        swal({
            title: 'Are you sure?',
            text: 'Please, confirm if you want to delete this board.',
            type: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#DD6B55',
            confirmButtonText: 'Yes, delete it!',
            closeOnConfirm: false
        }, function() {
            var data = {csrfmiddlewaretoken: Cookies.get('csrftoken')};
            $.post(action, data).done(function() {
                table.api().rows('#board-row-' + boardId).remove().draw();
                swal('Deleted!', 'The board has been deleted.', 'success');
            });
        });
    });
});
