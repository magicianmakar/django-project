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
            url: api_url('store-add', 'gear'),
            type: 'POST',
            data: $('#store-create-form').serialize(),
            success: function(data) {
                window.location.reload(true);
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
        $.get(api_url('store', 'gear'), {id: storeId}).done(function(data) {
            $('#store-update-modal').modal('show');
            $('#store-update-form input[name="id"]').val(data.id);
            $('#store-update-form input[name="title"]').val(data.title);
            $('#store-update-form input[name="api_token"]').val(data.api_token);
        });
    });

    $('#store-update-form').on('submit', function(e) {
        $('#store-update-form [type=submit]').button('loading');

        $.ajax({
            url: api_url('store-update', 'gear'),
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
                url: api_url('store', 'gear') + '?' + $.param({id: storeId}),
                method: 'DELETE',
                success: function() {
                    $('#store-row-' + storeId).hide();
                    swal('Deleted!', 'The store has been deleted.', 'success');
                }
            });
        });
    });

    function updateUserStatistics(statistics_data) {
        $.each(statistics_data, function (i, store_info) {
            console.log(store_info);
            $('#orders_pending_' + store_info.id).html(store_info.pending_orders).parents('.statistics-link').toggle(true);
            $('#products_saved_' + store_info.id).html(store_info.products_saved).parents('.statistics-link').toggle(true);
            $('#products_connected_' + store_info.id).html(store_info.products_connected).parents('.statistics-link').toggle(true);
        });
    }

    if (user_statistics) {
        updateUserStatistics(user_statistics);
    } else {
        var pusher = new Pusher(sub_conf.key);
        var channel = pusher.subscribe(sub_conf.channel);
        var pending_order_task_id = null;

        channel.bind('gear-user-statistics-calculated', function(data) {
            if (pending_order_task_id === data.task) {
                $.ajax({
                    url: api_url('user-statistics', 'gear'),
                    type: 'GET',
                    data: {
                        cache_only: true
                    },
                    success: function(data) {
                        if (data.stores) {
                            updateUserStatistics(data.stores);
                        }
                    }
                });
            }
        });

        channel.bind('pusher:subscription_succeeded', function() {
            $.ajax({
                url: api_url('user-statistics', 'gear'),
                type: 'GET',
                success: function(data) {
                    if (data.task) {
                        pending_order_task_id = data.task;
                    } else if (data.stores) {
                        updateUserStatistics(data.stores);
                    }
                }
            });
        });
    }
});
