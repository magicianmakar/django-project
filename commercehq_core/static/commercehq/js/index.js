(function() {
    'use strict';

    $('.add-store-btn').click(function (e) {
        e.preventDefault();
        $('#add-store').show();
        $('#update-store').hide();
        $('#store-name').val('');
        $('#store-url').val('');
        $('#store-key').val('');
        $('#store-password').val('');
        $('#modal-add-store-form').modal('show');
        console.log('Clicked')
    });

    $('#add-store').click(function(e) {
        var name = $('#store-name');
        var url = $('#store-url')//.match(/^[\w\-]+\.commercehq\.com/);
        var key = $('#store-key');
        var password = $('#store-password');
        /**
        if (!url || url.length != 1) {
            swal('Add Store', 'API URL is not correct!', 'error');
            return;
        } else {
            url = 'https://' + url[0];
        }**/

        $('#add-store').button('loading');

        $.ajax({
            url: '/chq/api/add-store',
            type: 'POST',
            headers: {'X-CSRFToken': Cookies.get('csrftoken')},
            data: {
                title: name.val().trim(),
                url: url.val().trim(),
                api_key: key.val().trim(),
                api_password: password.val().trim()
            },
            success: function(data) {
                if ('error' in data) {
                    data.error.url.forEach(function(value) {
                        console.log(url)
                        url.append('<p/>').html(value);
                    });
                } else {
                    window.location.reload();
                }
            },
            error: function(data) {
                displayAjaxError('Add Store', data);
            },
            complete: function () {
                $('#add-store').button('reset');
            }
        });
    });

})();
