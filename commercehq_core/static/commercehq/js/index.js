$(document).ready(function() {
    'use strict';

    $('.add-store-btn').click(function(e) {
        e.preventDefault();
        if ($(this).data('extra')) {
            swal({
                title: "Additional Store",
                text: "You are about to add an additional store to your plan for <b>$27/month</b>, Would you like to continue?",
                type: "info",
                html: true,
                showCancelButton: true,
                closeOnCancel: true,
                closeOnConfirm: true,
                animation: false,
                showLoaderOnConfirm: true,
                confirmButtonText: "Yes, Add This Store",
                cancelButtonText: "Cancel"
            }, function(isConfirmed) {
                if (!isConfirmed) return;
                $('#store-create-modal').modal('show');
            });
        } else {
            $('#store-create-modal').modal('show');
        }
    });

    $('.edit-store-btn').click(function(e) {
        e.preventDefault();
        var action = $(this).data('store-update-url');

        $('#store-update-form').prop('action', action);

        $.get(action)
            .done(function(data) {
                $('#store-update-form').html(data);
                $('#store-update-modal').modal('show');
            })
            .fail(function(jqXHR) {
                if (jqXHR.status == 401) {
                    window.location.reload();
                }
            });
    });

    $('.delete-store-btn').click(function(e) {
        e.preventDefault();
        var storeId = $(this).data('store-id');
        var action = $(this).data('store-delete-url');

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
            if (xhr.status == 204) {
                window.location.reload();
            }
        }
    });

    $('#store-update-form').ajaxForm({
        target: '#store-update-form',
        clearForm: true,
        data: {csrfmiddlewaretoken: Cookies.get('csrftoken')},
        success: function(responseText, statusText, xhr, $form) {
            if (xhr.status == 204) {
                window.location.reload();
            }
        }
    });
});
