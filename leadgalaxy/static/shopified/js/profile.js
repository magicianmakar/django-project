$(function () {
    $('#country, #timezone').chosen({
        search_contains: true,
        width: '250px'
    });

    $('#country').trigger('change');

    if (getQueryVariable('plan')) {
        $('.plan-tab a').trigger('click');
    } else if (getQueryVariable('billing')) {
        $('.billing-tab a').trigger('click');
    }

    if(getQueryVariable('w') == '1' && Cookies.get('welcome') != '1') {
        setTimeout(function() {
            Cookies.set('welcome', '1', { expires: 1 });

            swal('Congrats!', 'You are now registered. Your next step is to choose ' +
                'the plan that you would like to use for your 14 day free trial. \n'+
                'No credit card is required.', 'success');
        }, 500);
    }

    $('#company_country').chosen({
        search_contains: true,
        width: '250px'
    });
});

$('#country').change(function (e) {
    var el = $(e.target);

    $.ajax({
        url: '/api/timezones',
        type: 'GET',
        data: {'country': el.val()},
        context: {el: el},
        success: function (data) {
            $('#timezone').empty();

            if (!el.attr('current') && !el.attr('current').length && !el.val().length) {
                $('#timezone').append($('<option>'));
            }

            $.each(data, function (i, tz) {
                var op = $('<option>', {value: tz[0], text: tz[1]});
                if (el.attr('current') == tz[0]) {
                    op.prop('selected', true);
                }

                $('#timezone').append(op);
            });

            $('#timezone').trigger("chosen:updated");
        }
    });
});

$('#save-profile').click(function () {
    var btn = $(this);
    btn.button('loading');

    $.ajax({
        url: '/api/user-profile',
        type: 'POST',
        data: $('form#user-profile').serialize(),
        context: {btn: btn},
        success: function (data) {
            if (data.status == 'ok') {
                toastr.success('Saved', 'User Profile');
                if (data.reload) {
                    window.location.reload();
                }
            } else {
                displayAjaxError('User Profile', data);
            }
        },
        error: function (data) {
            displayAjaxError('User Profile', data);
        },
        complete: function () {
            this.btn.button('reset');
        }
    });
});

$('#save-email').click(function () {
    var btn = $(this);
    btn.button('loading');

    $.ajax({
        url: '/api/user-email',
        type: 'POST',
        data: $('form#user-email').serialize(),
        context: {btn: btn},
        success: function (data) {
            if (data.status == 'ok') {
                var msg = '';
                if (data.email) {
                    msg = 'Email ';
                }

                if  (data.password) {
                    if (msg.length > 0) {
                        msg += 'and ';
                    }

                    msg += 'Password ';
                }

                if (msg.length > 0) {
                    toastr.success(msg + 'Changed', 'Email & Password');
                    window.location.reload();
                } else {
                    toastr.warning('No Change made', 'Email & Password');
                }
            } else {
                if (typeof(data.error) == 'string') {
                    displayAjaxError('Email & Password', data);
                } else {
                    var error_msg = '';
                    $.each(data.error, function (i, el) {
                        error_msg += i + ': ' + el + "\n";
                    });

                    displayAjaxError('Email & Password', error_msg);
                }
            }
        },
        error: function (data) {
            displayAjaxError('Email & Password', data);
        },
        complete: function () {
            this.btn.button('reset');
        }
    });
});


$('#renew_clippingmagic').click( function() {
    var plan = $("#clippingmagic_plan option:selected").val();
    if (!plan) {
        swal('Clippingmagic Credits', 'Please select a credit to purchase first.', 'warning');
        return;
    }
    $.ajax({
        url: '/subscription/clippingmagic_subscription',
        type: 'POST',
        data: {
            'plan': plan
        },
        success: function (data) {
            toastr.success('Credit Purchase Complete!', 'Clippingmagic Credits');

            setTimeout(function() {
                window.location.reload();
            }, 1000);
        },
        error: function (data) {
            displayAjaxError('Clippingmagic Credits', data);
        }
    });
});
