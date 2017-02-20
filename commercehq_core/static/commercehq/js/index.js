$(document).ready(function() {
    'use strict';

    $('.add-store-btn').click(function(e) {
        e.preventDefault();
        $('#store-create-modal').modal('show');
    });

    $('.edit-store').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');
        var action = '/chq/store-update/' + storeId;

        $('#store-update-form').prop('action', action);

        $.get(action).then(function(data) {
            $('#store-update-form').html(data);
            $('#store-update-modal').modal('show');
        })
    });

    $('.delete-store').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');
        var action = '/chq/store-delete/' + storeId;

        swal({
            title: 'Are you sure?',
            text: 'Please, confirm if you want to delete this store.',
            type: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#DD6B55',
            confirmButtonText: 'Yes, delete it!',
            closeOnConfirm: false
        }, function() {
            var data = {csrfmiddlewaretoken: Cookies.get('csrftoken')};
            $.post(action, data).done(function() {
                $('#store-row-' + storeId).hide();
                swal('Deleted!', 'The store has been deleted.', 'success');
            });
        });
    });

    $('#store-create-form').ajaxForm({
        target: '#store-create-form',
        clearForm: true,
        data: {csrfmiddlewaretoken: Cookies.get('csrftoken')},
        success: function(responseText, statusText, xhr, $form) {
            if (xhr.status == 201) {
                window.location.reload();
            }
        }
    });

    $('#store-update-form').ajaxForm({
        target: '#store-update-form',
        clearForm: true,
        data: {csrfmiddlewaretoken: Cookies.get('csrftoken')},
        success: function(responseText, statusText, xhr, $form) {
            if (xhr.status == 201) {
                window.location.reload();
            }
        }
    });
});
