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

    $('.country_list').chosen({
        search_contains: true,
        width: '250px'
    });

    checkSelectedMenu(window.location.hash);

    var callflex_anchor = window.location.href.match(/callflex_anchor/);
    if(callflex_anchor) {
        $('.plan-tab a').tab('show');
        $('.callflex-anchor').get(0).scrollIntoView();
    }
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
    userProfileForm = $('form#user-profile')[0];
    var formData = new FormData(userProfileForm);
    $.ajax({
        url: '/api/user-profile',
        type: 'POST',
        processData: false,
        contentType: false,
        data: formData,
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
        data: {
            ali_email: $('#ali_email').val(),
            ali_pass: $('#ali_pass').val(),
        },
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

$('#renew_clippingmagic, #renew_captchacredit, #renew_callflexcredit, #renew_callflexnumber').click(function() {
    var type = $(this).attr('id').split('_')[1];
    var title = $(this).data('title');
    var option = $('#' + type + '_plan option:selected');
    var plan = option.val();
    var have_billing_info = $(this).data('cc');
    var shopify_billing = $(this).data('shopify');

    if (!plan) {
        swal(title, 'Please select a credit to purchase first.', 'warning');
        return;
    }

    if(!shopify_billing && !have_billing_info) {
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

    var payement_method = shopify_billing ? 'Shopify Account' : 'Credit Card';
    swal({
        title: "Purchase " + option.data('credits') + " Credits",
        text: "Your " + payement_method + " will be charged " + option.data('amount') + '\nContinue with the purchase?',
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
                    if (!data.location) {
                        toastr.success('Credit Purchase Complete!', title);
                        swal.close();
                    }

                    setTimeout(function() {
                        if (data.location) {
                            window.location.href = data.location;
                        } else {
                            window.location.reload();
                        }

                    }, 1500);
                },
                error: function(data) {
                    displayAjaxError(title, data);
                }
            });
        }
    });
});

function checkSelectedMenu(selectedMenu) {
    selectedMenu = selectedMenu.replace('#', '');
    $('.profile-submenus').removeClass('active');
    if (selectedMenu == 'billing') {
        $('#profile-billing').addClass('active');
        $('.billing-tab a').trigger('click');
    } else if (selectedMenu == 'plan') {
        $('#profile-plans').addClass('active');
        $('.plan-tab a').trigger('click');
    } else if (selectedMenu == 'invoices') {
        $('#profile-invoices').addClass('active');
        $('.invoices-tab a').trigger('click');
    } else {
        $('#menu-profile').addClass('active');
    }
}

$('.profile-submenus').on('click', function() {
    setTimeout(function() {
        checkSelectedMenu(window.location.hash);
    }, 1);
});

$('.panel-toggle .panel-heading').click(function (e) {
    e.preventDefault();

    $(e.currentTarget).parent().find('.panel-body').toggleClass('hidden');
}).css('cursor', 'pointer');

$('#accounts-menu a').on('click', function(e) {
    var menuLink = $(this).attr('data-href');
    if (menuLink) {
        e.preventDefault();
        $('a[href="' + menuLink + '"]').trigger('click');
    }
});

if (window.location.hash === '#user') {
    $('[name="first_name"]').parent('.form-group').addClass('has-error');
    $('[name="last_name"]').parent('.form-group').addClass('has-error');
}
