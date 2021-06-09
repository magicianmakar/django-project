$(document).ready(function () {

    $('.change-plan-btn').click(function (e) {
        e.preventDefault();

        $('.active-plan-change').removeClass('active-plan-change');
        $(this).parents('tr').find('.profile-plan').addClass('active-plan-change');
        $('#modal-plan-select').prop('user-id', $(this).attr('user-id')).modal('show');
    });

    $('.add-bundle-btn').click(function (e) {
        e.preventDefault();

        $('#modal-bundle-select').prop('user-id', $(this).attr('user-id')).modal('show');
    });

    $('.deactivate-account').click(function (e) {
        e.preventDefault();

        var user_id = $(this).attr('user-id');
        swal({
                title: "Deactivate Account",
                text: 'This will prevent user from login, all his data will be preserved, and account can be re-activated. Contuine?',
                type: "warning",
                showCancelButton: true,
                closeOnCancel: true,
                closeOnConfirm: false,
                confirmButtonColor: "#DD6B55",
                confirmButtonText: "Deactivate",
                cancelButtonText: "Cancel"
            },
            function (isConfirmed) {
                if (isConfirmed) {

                    $.ajax({
                        type: 'POST',
                        url: api_url('deactivate-account', 'acp'),
                        data: {
                            'user': user_id
                        },
                        success: function (data) {
                            swal('Deactivate Account', 'Deactivated', 'success');
                            window.location.reload();
                        },
                        error: function (data) {
                            displayAjaxError('Deactivate Account', data);
                        },
                    });
                }
            });
    });

    $('.activate-account').click(function (e) {
        e.preventDefault();

        var user_id = $(this).attr('user-id');
        $.ajax({
            type: 'POST',
            url: api_url('activate-account', 'acp'),
            data: {
                'user': user_id
            },
            success: function (data) {
                swal('Activate Account', 'Activated', 'success');
                window.location.reload();
            },
            error: function (data) {
                displayAjaxError('Activate Account', data);
            },
        });
    });

    $('.toggle-plod').click(function (e) {
        e.preventDefault();

        var user_id = $(this).attr('user-id');
        $.ajax({
            type: 'POST',
            url: api_url('toggle-plod', 'acp'),
            data: {
                'user': user_id
            },
            success: function (data) {
                swal('Toggle PLoD', 'Done', 'success');
                window.location.reload();
            },
            error: function (data) {
                displayAjaxError('Toggle PLoD', data);
            },
        });
    });

    $('.login-as').click(function (e) {
        e.preventDefault();

        var user_id = $(this).attr('user-id');
        $.ajax({
            type: 'POST',
            url: api_url('login-as', 'acp'),
            data: {
                'user': user_id
            },
            success: function (data) {
                window.location.href = data.url;
            },
            error: function (data) {
                displayAjaxError('Login As User', data);
            },
        });
    });

    $('.allow-trial-btn').click(function (e) {
        e.preventDefault();

        var user_id = $(this).attr('user-id');
        swal({
                title: "Allow Free Trial",
                text: 'Allow user to have an other trial subscription?',
                type: "warning",
                showCancelButton: true,
                closeOnCancel: true,
                closeOnConfirm: false,
                confirmButtonText: "Yes",
                cancelButtonText: "Cancel"
            },
            function (isConfirmed) {
                if (isConfirmed) {

                    $.ajax({
                        type: 'POST',
                        url: '/api/change-plan',
                        data: {'user': user_id, 'allow_trial': true},
                        success: function (data) {
                            swal('Allow Free Trial', 'User can now have free trial', 'success');
                        },
                        error: function (data) {
                            displayAjaxError('Allow Free Trial', data);
                        },
                    });
                }
            });
    });

    $('.reset-auto-fulfill').click(function (e) {
        e.preventDefault();

        var user_id = $(this).attr('user-id');
        swal({
                title: "Auto Fulfill Limit",
                text: 'Reset this month auto fulfill limit?',
                type: "warning",
                showCancelButton: true,
                closeOnCancel: true,
                closeOnConfirm: false,
                confirmButtonText: "Yes",
                cancelButtonText: "Cancel"
            },
            function (isConfirmed) {
                if (isConfirmed) {

                    $.ajax({
                        type: 'POST',
                        url: '/api/auto-fulfill-limit-reset',
                        data: {'user': user_id},
                        success: function (data) {
                            swal('Auto Fulfill Limit', 'Limit was reseted', 'success');
                        },
                        error: function (data) {
                            displayAjaxError('Auto Fulfill Limit', data);
                        },
                    });
                }
            });
    });

    $('.release-sub-user').click(function (e) {
        e.preventDefault();

        var user_id = $(this).attr('user-id');
        swal({
                title: "Release Sub User",
                text: 'Release this Sub User?',
                type: "warning",
                showCancelButton: true,
                closeOnCancel: true,
                closeOnConfirm: false,
                confirmButtonText: "Yes",
                cancelButtonText: "Cancel"
            },
            function (isConfirmed) {
                if (isConfirmed) {

                    $.ajax({
                        type: 'POST',
                        url: '/api/release-subuser',
                        data: {'user': user_id},
                        success: function (data) {
                            swal('Release Sub User', 'User has been released', 'success');
                        },
                        error: function (data) {
                            displayAjaxError('Release Sub User', data);
                        },
                    });
                }
            });
    });

    $('#change-plan-apply').click(function (e) {
        var btn = $(this);
        var user = $('#modal-plan-select').prop('user-id');
        var plan = $('#plan-change-select').val();

        btn.button('loading');

        $.ajax({
            type: 'POST',
            url: '/api/change-plan',
            context: {},
            data: {
                'plan': plan,
                'user': user
            },
            success: function (data) {
                if (data.status == 'ok') {
                    $('#modal-plan-select').modal('hide');
                    $('.active-plan-change').find('b').text(data.plan.title);

                    toastr.success('User plan changed to: <b>' + data.plan.title + '</b>', 'Change Plan');
                } else {
                    displayAjaxError('Change Plan', data);
                }
            },
            error: function (data) {
                displayAjaxError('Change Plan', data);
            },
            complete: function () {
                btn.button('reset');
            }
        });
    });

    $('#select-bundle-apply').click(function (e) {
        var btn = $(this);
        var user = $('#modal-bundle-select').prop('user-id');
        var bundle = $('#modal-bundle-select select').val();

        btn.button('loading');

        $.ajax({
            type: 'POST',
            url: '/api/add-bundle',
            context: {},
            data: {
                'bundle': bundle,
                'user': user
            },
            success: function (data) {
                toastr.success('Bundle Added');
                $('#modal-bundle-select').modal('hide');
            },
            error: function (data) {
                displayAjaxError('Add Bundle', data);
            },
            complete: function () {
                btn.button('reset');
            }
        });
    });

    $('.intercom-btn').click(function (e) {
        e.preventDefault();

        var data = {
            "predicates": [
                {
                    "comparison": "eq",
                    "value": $(e.target).data('email'),
                    "attribute": "email",
                    "type": "string"
                },
                {
                    "type": "anonymous",
                    "comparison": "false",
                    "value": null,
                    "attribute": "anonymous"
                }
            ]
        };

        window.open('https://app.intercom.io/a/apps/k9cb5frr/users/segments/all:' + btoa(JSON.stringify(data)), '_blank');
    });

    $('.cancel-subscription-btn').click(function (e) {
        e.preventDefault();

        var btn = $(e.currentTarget);

        swal({
            title: "Cancel Subscription",
            text: "Are you sure you want to cancel this user subscription?\nSubscription will cancel " +
                (btn.data('cancel-now') ? 'immediately' : 'when billing cycle ends'),
            type: "warning",
            showCancelButton: true,
            closeOnConfirm: false,
            animation: "slide-from-top",
            showLoaderOnConfirm: true
        }, function (inputValue) {
            if (inputValue === false || !inputValue) return false;

            $.ajax({
                url: '/api/stripe-cancel-subscription',
                type: 'POST',
                data: {
                    id: $(e.target).attr('charge-id'),
                    user: $(e.target).attr('user-id'),
                    now: !!btn.data('cancel-now'),
                },
            }).done(function (data) {
                toastr.success('Reloading page...', 'Subscription Canceled');
                swal.close();

                setTimeout(function () {
                    window.location.reload();
                }, 1000);
            }).fail(function (data) {
                displayAjaxError('Cancel Subscription', data);
            });
        });
    });

    $('.registration-apply-btn').click(function (e) {
        e.preventDefault();

        swal({
            title: "Apply Registration",
            text: "Are you sure you want to apply this Registration?",
            type: "warning",
            showCancelButton: true,
            closeOnConfirm: false,
            animation: "slide-from-top",
            showLoaderOnConfirm: true
        }, function (inputValue) {
            if (inputValue === false || !inputValue) return false;

            $.ajax({
                url: '/api/apply-registration',
                type: 'POST',
                data: {
                    id: $(e.target).attr('register-id'),
                    user: $(e.target).attr('user-id'),
                },
            }).done(function (data) {
                toastr.success('Reloading page...', 'Registration Applied');
                swal.close();

                setTimeout(function () {
                    window.location.reload();
                }, 1000);
            }).fail(function (data) {
                displayAjaxError('Apply Registration', data);
            });
        });
    });

    $('.refund-charge-btn').click(function (e) {
        e.preventDefault();

        var clean_money = function (s) {
            return parseFloat(s.replace(/[^0-9,\.]/, '')) || 0.0;
        };

        var refund = clean_money($(e.target).attr('refund-amount')) - clean_money($(e.target).attr('refunded-amount'));

        swal({
            title: "Refund Charge",
            text: "Amount to Refund:",
            type: "input",
            inputValue: refund.toFixed(2),
            showCancelButton: true,
            closeOnConfirm: false,
            animation: "slide-from-top",
            inputPlaceholder: "Amount",
            showLoaderOnConfirm: true
        }, function (inputValue) {
            if (inputValue === false) return false;
            inputValue = inputValue.trim();

            if (inputValue === "") {
                swal.showInputError("You need to enter an amount.");
                return false;
            }

            inputValue = parseFloat(inputValue);
            if (!inputValue) {
                swal.showInputError("The entered amount is invalid.");
                return false;
            }

            $.ajax({
                url: '/api/stripe-refund-charge',
                type: 'POST',
                data: {
                    id: $(e.target).attr('charge-id'),
                    user: $(e.target).attr('user-id'),
                    amount: inputValue
                },
            }).done(function (data) {
                toastr.success('$' + inputValue + ' Refunded', 'Amount Refunded');
                swal.close();

                setTimeout(function () {
                    window.location.reload();
                }, 1000);
            }).fail(function (data) {
                displayAjaxError('Charge Refund', data);
            });
        });
    });

    $('.change-customer-id-btn').click(function (e) {
        e.preventDefault();

        swal({
            title: "Change Customer ID",
            text: "Are you sure you want to change this Customer ID?",
            type: "warning",
            showCancelButton: true,
            closeOnConfirm: false,
            animation: "slide-from-top",
            showLoaderOnConfirm: true
        }, function (inputValue) {
            if (inputValue === false || !inputValue) return false;

            $.ajax({
                url: '/api/change-customer-id',
                type: 'POST',
                data: {
                    'customer-id': $(e.target).attr('customer-id'),
                    'user': $(e.target).attr('user-id'),
                    'convert': $(e.target).data('convert'),
                },
            }).done(function (data) {
                toastr.success('Changed!', 'Customer ID');
                swal.close();
            }).fail(function (data) {
                displayAjaxError('Customer ID Change', data);
            });
        });
    });

    $('.convert-to-stripe-btn').click(function (e) {
        e.preventDefault();

        swal({
            title: "Convert to Stripe",
            text: "Are you sure you want to convert this user to Stripe?",
            type: "warning",
            showCancelButton: true,
            closeOnConfirm: false,
            animation: "slide-from-top",
            showLoaderOnConfirm: true
        }, function (inputValue) {
            if (inputValue === false || !inputValue) return false;

            $.ajax({
                url: '/api/convert-to-strip',
                type: 'POST',
                data: {
                    'customer-id': $(e.target).attr('customer-id'),
                    'user': $(e.target).attr('user-id'),
                },
            }).done(function (data) {
                toastr.success('Converted!', 'Convert to Stripe');
                swal.close();
                window.location.reload();
            }).fail(function (data) {
                displayAjaxError('Convert to Stripe', data);
            });
        });
    });

    $('.reset-customer-balance-btn').click(function (e) {
        e.preventDefault();

        swal({
            title: "Reset Customer Balance",
            text: "Are you sure you want to reset this Customer balance in Stripe?",
            type: "warning",
            showCancelButton: true,
            closeOnConfirm: false,
            animation: "slide-from-top",
            showLoaderOnConfirm: true
        }, function (inputValue) {
            if (inputValue === false || !inputValue) return false;

            $.ajax({
                url: '/api/reset-customer-balance',
                type: 'POST',
                data: {
                    'customer-id': $(e.target).attr('customer-id'),
                    'user': $(e.target).attr('user-id'),
                },
            }).done(function (data) {
                toastr.success('Reseted!', 'Customer Balance');
                window.location.reload();
                swal.close();
            }).fail(function (data) {
                displayAjaxError('Customer Balance', data);
            });
        });
    });

    $('.btn-remove-addon').click(function (e) {
        e.preventDefault();

        var btn = $(e.currentTarget);
        var addonTitle = btn.data('title');
        var addonId = btn.data('addon-id');
        var userId = btn.data('user-id');

        swal({
            title: "Remove Addon",
            text: "Are you sure you want to remove " + addonTitle + " addon from this user account?",
            type: "warning",
            showCancelButton: true,
            closeOnConfirm: false,
            animation: "slide-from-top",
            showLoaderOnConfirm: true
        }, function (inputValue) {
            if (inputValue === false || !inputValue) return false;

            $.ajax({
                url: api_url('addon', 'acp'),
                type: 'DELETE',
                data: {
                    'addon': addonId,
                    'user': userId,
                },
            }).done(function (data) {
                toastr.success('Deleted!', 'Remove Addon');
                btn.parents('.user-addon').remove();
                swal.close();
            }).fail(function (data) {
                displayAjaxError('Remove Addon', data);
            });
        });
    });

    if (getQueryVariable('user') && getQueryVariable('bundle') && getQueryVariable('auto') === 'bundle') {
        $.ajax({
            type: 'POST',
            url: '/api/add-bundle',
            data: {
                'bundle': getQueryVariable('bundle'),
                'user': getQueryVariable('user')
            },
            success: function (data) {
                swal('Bundle ' + data.bundle.title + ' add to ' + data.user.email);
            },
            error: function (data) {
                displayAjaxError('Add Bundle', data);
            }
        });
    }
});
