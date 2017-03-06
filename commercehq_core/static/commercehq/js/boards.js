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

    $("#chq-new-board-add-form").submit(function(e) {
        e.preventDefault();
        var $title = $(this).find('input[name="title"]');
        var boardName = $title.val().trim();

        $.ajax({
            url: api_url('boards-add', 'chq'),
            type: 'POST',
            data: {title: boardName},
            success: function(data) {
                if ('status' in data && data.status == 'ok') {
                    $('#chq-modal-board-add').modal('hide');
                    $title.val('');

                    if (typeof(window.onBoardAdd) == 'function') {
                        window.onBoardAdd(data.board);
                    } else {
                        window.location.href = window.location.href;
                    }
                } else {
                    displayAjaxError('Create Board', data);
                }
            },
            error: function (data) {
                displayAjaxError('Create Board', data);
            }
        });
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

        swal({
            title: 'Are you sure?',
            text: 'Please, confirm if you want to delete this board.',
            type: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#DD6B55',
            confirmButtonText: 'Yes, delete it!',
            closeOnConfirm: false
        }, function() {
            $.ajax({
                url: api_url('board', 'chq') + '?board_id=' + boardId,
                method: 'DELETE',
                success: function(data) {
                    if ('status' in data && data.status == 'ok') {
                        table.api().rows('#board-row-' + boardId).remove().draw();
                        swal.close();
                        toastr.success('Board has been deleted.', 'Delete Board');
                    } else {
                        displayAjaxError('Delete Board', data);
                    }
                },
                error: function (data) {
                    displayAjaxError('Delete Board', data);
                }
            });
        });
    });

    $('.chq-empty-board-btn').click(function(e) {
        e.preventDefault();
        var boardId = $(this).data('board-id');

        swal({
            title: "Empty Board",
            text: "This will empty the board from its products. \n" +
                  "The products are not deleted from your account. \n" +
                  "Are you sure you want to empty the board?",
            type: "warning",
            showCancelButton: true,
            confirmButtonColor: "#DD6B55",
            confirmButtonText: "Empty Board",
            closeOnConfirm: false
        }, function() {
            $.ajax({
                url: api_url('board-empty', 'chq'),
                data: {board_id: boardId},
                method: 'POST',
                success: function(data) {
                    if ('status' in data && data.status == 'ok') {
                        swal.close();
                        toastr.success("The board is now empty.", "Empty Board");
                        $('#board-row-' + boardId).find('.product-count').html('0');
                    } else {
                        displayAjaxError('Empty Board', data);
                    }
                },
                error: function (data) {
                    displayAjaxError('Empty Board', data);
                }
            });
        });
    });
});
