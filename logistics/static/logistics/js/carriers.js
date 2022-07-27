$('#add-carrier-modal').on('show.bs.modal', function() {
    $('#add-carrier-modal form').trigger('reset');
    $('#carrier-credentials').empty();
});

$('#add-carrier-modal form').on('submit', function(e) {
    e.preventDefault();

    var form = $(this);
    $.ajax({
        url: api_url('carrier', 'logistics'),
        type: 'POST',
        data: form.serialize(),
        success: function(data) {
            if (!data.errors || !data.errors.length) {
                window.location.reload();
                return true;
            }

            $('#add-carrier-modal .modal-content').removeClass('loading');
            if (data.errors.length === undefined) {
                for (var field in data.errors) {
                    var errors = data.errors[field];
                    var fieldElem = $('#add-carrier-modal form [name="' + field + '"]');
                    if (!fieldElem.length) {
                        fieldElem = $('#add-carrier-modal form [name="credentials_' + field + '"]');
                    }
                    fieldElem.parents('.form-group').addClass('has-error');
                    for (var i = 0, iLength = errors.length; i < iLength; i++) {
                        fieldElem.after($('<p class="help-block">').text(errors[i]));
                    }
                }
            } else {
                for (var j = 0, jLength = data.errors.length; j < jLength; j++) {
                    $('#add-carrier-modal .modal-body').prepend($('<div class="alert alert-danger">').text(data.errors[j]));
                }
            }
        },
        beforeSend: function() {
            $('#add-carrier-modal .modal-content').addClass('loading');
            $('#add-carrier-modal form .has-error p').remove();
            $('#add-carrier-modal form .has-error').removeClass('has-error');
            $('#add-carrier-modal .modal-body .alert-danger').remove();
        },
        error: function(data) {
            $('#add-carrier-modal .modal-content').removeClass('loading');
            displayAjaxError('Create Carrier', data);
        }
    });
});

$('.delete-carrier').on('click', function (e) {
    e.preventDefault();

    var btn = $(this);
    swal({
        title: 'Delete Carrier',
        text: 'Are you sure you want to delete this Carrier?',
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
                url: api_url('carrier', 'logistics'),
                data: {'id': btn.data('id')},
                context: btn,
                success: function(data) {
                    toastr.success('Carrier Deleted.');
                    swal.close();
                    btn.parents('tr').remove();
                },
                error: function(data) {
                    displayAjaxError('Delete Carrier', data);
                }
            });
        }
    });
});

$('[name="carrier_type"]').on('change', function() {
    $('#carrier-credentials').empty();
    var carrierId = parseInt($(this).val());
    var carrierType = null;
    for (var i = 0, iLength = carrierTypes.length; i < iLength; i++) {
        if (carrierTypes[i].id === carrierId) {
            carrierType = carrierTypes[i];
            break;
        }
    }

    if (carrierType && carrierType.fields) {
        for (var j = 0, jLength = carrierType.fields.length; j < jLength; j++) {
            var field = carrierType.fields[j];
            var fieldLabel = $('<label>');
            var fieldElem = $('<div class="form-group">').append(fieldLabel);
            if (field.type === 'checkbox') {
                fieldLabel.append($('<input class="icheck" type="checkbox" name="credentials_' + field.name + '" value="1">'), field.label);
                fieldElem.addClass('checkbox').removeClass('form-group');
            } else {
                fieldLabel.text(field.label + ':').attr('for', 'credentials_' + field.name);
                fieldElem.append($('<input type="' + field.type + '" name="credentials_' + field.name + '" class="form-control">'));
            }
            $('#carrier-credentials').append(fieldElem);
        }
    }
});
