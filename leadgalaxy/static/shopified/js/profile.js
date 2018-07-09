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

            swal({
                title: "Congrats!",
                type: "success",
                confirmButtonText: "Yes I'm Ready",
                text: "You are now registered. \nYour next step is to GET ROLLING on the START UP PLAN or \n" +
                      "IF you're READY to open up all our Killer features, select the Plan best for you & lets show you what we've got",
            });
        }, 500);
    }

    if (getQueryVariable('auto')) {
        $('a[data-auto-hash="billing"]').trigger('click');
        $('.add-cc-btn').trigger('click');

        window.sourceAddCallback = function (data) {
            window.skipPlanSelectConfirmation = true;
            $('[data-plan="' + getQueryVariable('auto') + '"] button').trigger('click');
        };
    }

    if (getQueryVariable('try')) {
        window.skipPlanSelectConfirmation = true;
        $('[data-plan="' + getQueryVariable('try') + '"] button').trigger('click');
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

$('#save-dropwow-integration').click(function() {
    var btn = $(this);
    btn.button('loading');

    $.ajax({
        url: '/api/dropwow-integration',
        type: 'POST',
        data: $('form#dropwow-integration').serialize(),
        context: {
            btn: btn
        },
        success: function(data) {
            toastr.success('Dropwow Account Saved', 'Dropwow Account');
        },
        error: function(data) {
            displayAjaxError('Dropwow Account', data);
        },
        complete: function() {
            this.btn.button('reset');
        }
    });
});

$('#save-youzign-integration').click(function () {
    var btn = $(this);
    btn.button('loading');

    $.ajax({
        url: '/api/youzign-integration',
        type: 'POST',
        data: $("form#youzign-integration").serialize(),
        success: function (data) {
            if (data.status == 'ok') {
                toastr.success('Saved.','YouZign Configuration');
            } else {
                displayAjaxError('YouZign Configuration', data);
            }
        },
        error: function (data) {
            displayAjaxError('YouZign Configuration', data);
        },
        complete: function () {
            btn.button('reset');
        }
    });

    return false;
});


$('#save-aliexpress-integration').click(function() {
    var btn = $(this);
    btn.button('loading');

    $.ajax({
        url: '/api/aliexpress-integration',
        type: 'POST',
        data: $('form#aliexpress-integration').serialize(),
        context: {
            btn: btn
        },
        success: function(data) {
            toastr.success('Aliexpress Account Saved', 'Aliepxress Account');
        },
        error: function(data) {
            displayAjaxError('Aliepxress Account', data);
        },
        complete: function() {
            this.btn.button('reset');
        }
    });
});

$('#renew_clippingmagic, #renew_captchacredit').click(function() {
    var type = $(this).attr('id').split('_')[1];
    var title = $(this).data('title');
    var option = $('#' + type + '_plan option:selected');
    var plan = option.val();
    var have_billing_info = $(this).data('cc');

    if (!plan) {
        swal(title, 'Please select a credit to purchase first.', 'warning');
        return;
    }

    if(!have_billing_info) {
        swal({
            title: title,
            text: "Add your credit card to purchase credits.",
            type: "warning",
            showCancelButton: true,
            closeOnConfirm: true,
            animation: false,
            confirmButtonColor: "#93c47d",
            confirmButtonText: "Add Credit Card",
            cancelButtonText: "No Thanks"
        },
        function(isConfirmed) {
            if (isConfirmed) {
                $('a[data-auto-hash="billing"]').trigger('click');
                $('.add-cc-btn').trigger('click');
            }
        });

        return;
    }

    swal({
        title: "Purchase " + option.data('credits') + " Credits",
        text: "Your Credit Card will be charged " + option.data('amount') + '\nContinue with the purchase?',
        type: "info",
        showCancelButton: true,
        closeOnConfirm: false,
        animation: false,
        showLoaderOnConfirm: true,
        confirmButtonColor: "#93c47d",
        confirmButtonText: "Yes",
        cancelButtonText: "No Thanks"
    },
    function(isConfirmed) {
        if (isConfirmed) {
            $.ajax({
                url: '/subscription/' + type + '_subscription',
                type: 'POST',
                data: {
                    'plan': plan
                },
                success: function(data) {
                    toastr.success('Credit Purchase Complete!', title);
                    swal.close();

                    setTimeout(function() {
                        window.location.reload();
                    }, 1500);
                },
                error: function(data) {
                    displayAjaxError(title, data);
                }
            });
        }
    });
});
