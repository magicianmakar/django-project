$.fn.bootstrapBtn = $.fn.button.noConflict();
$.fn.bootstrapTooltip = $.fn.tooltip.noConflict();


$('.addon-install, .addon-uninstall').click(function (e) {
    var btn = $(e.currentTarget);

    btn.bootstrapBtn('loading');
    var endpoint = btn.data('endpoint');

    $.ajax(api_url(endpoint.target, 'addons'),
        {
            type: 'post',
            data: {
                addon: btn.data('addon')
            }
        }).done(function (data) {
        window.location.reload();
    }).fail(function (data) {
        displayAjaxError(endpoint.name, data);
        btn.bootstrapBtn('reset');
    });
});

$('#add-addon-btn').click(function (e) {
    e.preventDefault();

    Swal.fire({
        title: 'Add New Addon',
        input: 'text',
        showCancelButton: true,
        confirmButtonText: 'Add',
        showLoaderOnConfirm: true,
        preConfirm: function preConfirm(title) {
            var formData = new FormData();
            formData.append('title', title);

            return fetch(api_url('add', 'addons'), {method: 'post', body: formData}).then(function (response) {
                if (!response.ok) {
                    throw new Error(response.statusText);
                }

                return response.json();
            }).catch(function (error) {
                Swal.showValidationMessage("Request failed: ".concat(error));
            });
        },
        allowOutsideClick: function allowOutsideClick() {
            return !Swal.isLoading();
        }
    }).then(function (result) {
        if (result.value.id) {
            window.location.href = '/addons/edit/' + result.value.slug;
        }
    });
});

$('#addon-edit-save').click(function (e) {
    e.preventDefault();

    var formData = new FormData();
    formData.append('addon-id', $('#addon-id').val());
    formData.append('addon-title', $('#addon-title').val());
    formData.append('addon-short', $('#addon-short').val());
    formData.append('addon-description', document.editor.getData());
    formData.append('addon-icon', $('#addon-icon').val());
    formData.append('addon-banner', $('#addon-banner').val());
    formData.append('addon-youtube', $('#addon-youtube').val());
    formData.append('addon-price', $('#addon-price').val());
    formData.append('addon-status', $('#addon-status').val());

    [0, 1, 2].forEach(function (i) {
        formData.append('addon-key-title-' + i, $('#addon-key-title-' + i).val());
        formData.append('addon-key-description-' + i, $('#addon-key-description-' + i).val());
        formData.append('addon-key-banner-' + i, $('#addon-key-banner-' + i).val());
    });

    fetch(api_url('edit', 'addons'), {
        method: 'post',
        body: formData
    }).then(function () {
        window.location.reload();
    }, function () {
        Swal.fire('Addon Edit', 'Could not save changes', 'error');
    });
});
