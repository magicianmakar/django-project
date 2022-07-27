$('#add-warehouse-modal').on('show.bs.modal', function() {
    $(this).find('form').trigger('reset');
});

$('#add-warehouse-modal form').on('submit', function(e) {
    e.preventDefault();

    var form = $(this);
    $.ajax({
        url: api_url('warehouse', 'logistics'),
        type: 'POST',
        data: form.serialize(),
        success: function(data) {
            if (!data.errors) {
                window.location.reload();
                return true;
            }

            $('#add-warehouse-modal .modal-content').removeClass('loading');
            if (data.errors.length === undefined) {
                for (var field in data.errors) {
                    var errors = data.errors[field];
                    var fieldElem = $('#add-warehouse-modal form [name="' + field + '"]');
                    fieldElem.parents('.form-group').addClass('has-error');
                    for (var i = 0, iLength = errors.length; i < iLength; i++) {
                        fieldElem.after($('<p class="help-block">').text(errors[i]));
                    }
                }
            } else {
                for (var j = 0, jLength = data.errors.length; j < jLength; j++) {
                    $('#add-warehouse-modal .modal-body').prepend($('<div class="alert alert-danger">').text(data.errors[j]));
                }
            }
        },
        beforeSend: function() {
            $('#add-warehouse-modal .modal-content').addClass('loading');
            $('#add-warehouse-modal form .has-error p').remove();
            $('#add-warehouse-modal form .has-error').removeClass('has-error');
            $('#add-warehouse-modal .modal-body .alert-danger').remove();
        },
        error: function(data) {
            $('#add-warehouse-modal .modal-content').removeClass('loading');
            displayAjaxError('Create Warehouse', data);
        }
    });
});

$('.delete-warehouse').on('click', function (e) {
    e.preventDefault();

    var btn = $(this);
    swal({
        title: 'Delete Warehouse',
        text: 'Are you sure you want to delete this Warehouse?',
        type: "warning",
        showCancelButton: true,
        animation: false,
        cancelButtonText: "Cancel",
        confirmButtonText: 'Yes',
        confirmButtonColor: "#DD6B55",
        closeOnCancel: true,
        closeOnConfirm: false,
        showLoaderOnConfirm: true,
    },
    function(isConfirm) {
        if (isConfirm) {

            $.ajax({
                type: 'DELETE',
                url: api_url('warehouse', 'logistics'),
                data: {'id': btn.data('id')},
                context: btn,
                success: function(data) {
                    toastr.success('Warehouse Deleted.');
                    swal.close();
                    btn.parents('tr').remove();
                },
                error: function(data) {
                    displayAjaxError('Delete Warehouse', data);
                }
            });
        }
    });
});

$('.edit-warehouse').on('click', function (e) {
    e.preventDefault();

    $.ajax({
        type: 'GET',
        url: api_url('warehouse', 'logistics'),
        data: {'id': $(this).data('id')},
        success: function(data) {
            $('#add-warehouse-modal').modal('show');

            for (var key in data) {
                $('#add-warehouse-modal form [name="' + key + '"]').val(data[key]);
            }
        },
        error: function(data) {
            displayAjaxError('Edit Warehouse', data);
        }
    });
});
