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
        $('#store-create-form [type=submit]').button('loading');

        $.ajax({
            url: api_url('store-add', 'woo'),
            type: 'POST',
            data: $('#store-create-form').serialize(),
            success: function(data) {
                window.location.replace(data.authorize_url);
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
        var storeId = $(this).data('store-id');
        $.get(api_url('store', 'woo'), {id: storeId}).done(function(data) {
            $('#store-update-modal').modal('show');
            $('#store-update-form input[name="id"]').val(data.id);
            $('#store-update-form input[name="title"]').val(data.title);
            $('#store-update-form input[name="api_url"]').val(data.api_url);
            $('#store-update-form input[name="api_key"]').val(data.api_key);
            $('#store-update-form input[name="api_password"]').val(data.api_password);
        });
    });

    $('#store-update-form').on('submit', function(e) {
        $('#store-update-form [type=submit]').button('loading');

        $.ajax({
            url: api_url('store-update', 'woo'),
            type: 'POST',
            data: $('#store-update-form').serialize(),
            success: function(data) {
                setTimeout(function() {
                    window.location.reload(true);
                }, 1000);
            },
            error: function(data) {
                $('#store-update-form [type=submit]').button('reset');
                displayAjaxError('Add Store', data);
            }
        });

        return false;
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
                url: api_url('store', 'woo') + '?' + $.param({id: storeId}),
                method: 'DELETE',
                success: function() {
                    $('#store-row-' + storeId).hide();
                    swal('Deleted!', 'The store has been deleted.', 'success');
                }
            });
        });
    });
});
