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

    $('#store-create-form').on('submit', function(e) {
        var url = $('#store_api_url').val().match(/[^\/\.]+\.commercehq(?:dev)?\.com/);

        if (!url || url.length != 1) {
            swal('Add Store', 'API URL is not correct!', 'error');
            return;
        }

        $('#store-create-form [type=submit]').button('loading');

        $.ajax({
            url: api_url('store-add', 'chq'),
            type: 'POST',
            data: $('#store-create-form').serialize(),
            success: function(data) {
                toastr.success('Add Store', 'Your Store Have Been Added!');
                setTimeout(function() {
                    window.location.reload();
                }, 1000);
            },
            error: function(data) {
                $('#store-create-form [type=submit]').button('reset');
                displayAjaxError('Add Store', data);
            }
        });

        return false;
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

        swal({
            title: 'Are you sure?',
            text: 'Please, confirm if you want to delete this store.',
            type: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#DD6B55',
            confirmButtonText: 'Yes, delete it!',
            closeOnConfirm: false
        }, function() {
            $.ajax({
                url: api_url('store', 'chq') + '?store_id=' + storeId,
                method: 'DELETE',
                success: function() {
                    $('#store-row-' + storeId).hide();
                    swal('Deleted!', 'The store has been deleted.', 'success');
                }
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
