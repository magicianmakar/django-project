(function(config) {
    function validateFullName(name) {
        if (!name || name.trim().length === 0) {
            return false;
        }

        return name.match(/[^ ]+ [^ ]+/) !== null;
    }

    function validateNonEmpty(name) {
        return name && name.trim().length !== 0;
    }

    function getStripeData() {
        return {
            number: $('.cc-number').val(),
            exp: $('.cc-exp').val(),
            cvc: $('.cc-cvc').val(),
            name: $('.cc-name').val(),

            address_line1: $('#address_line1').val(),
            address_line2: $('#address_line2').val(),
            address_city: $('#address_city').val(),
            address_state: $('#address_state').val(),
            address_zip: $('#address_zip').val(),
            address_country: $('#address_country').val(),
        };
    }

    function stripeResponseHandler(status, response) {

        if (response.error) {

            // Show the errors on the form
            $('#modal-billing .validation').append($('<li>', {
                'text': response.error.message
            })).show();
            $('#modal-billing .save-details').button('reset'); // Re-enable submission

            alert(response.error.message);

        } else {

            // Get the token ID:
            var token = response.id;

            $.ajax({
                url: config.customer_source,
                type: 'POST',
                data: {
                    stripeToken: token,
                },
                success: function(data) {
                    toastr.success("Billing Details have been updated.", "Billing Details");
                    $('#modal-billing').modal('hide');

                    if (window.sourceAddCallback) {
                        window.sourceAddCallback(data);
                    } else {
                        setTimeout(function() {
                            window.location.reload();
                        }, 1000);
                    }
                },
                error: function(data) {
                    displayAjaxError('Billing Details', data);
                },
                complete: function() {
                    $('#modal-billing .save-details').button('reset');
                }
            });

        }
    }

    $(function() {
        if (!config.hasOwnProperty('stripe')) {
            return;
        }

        Stripe.setPublishableKey(config.stripe);

        // $('.add-cc-btn').trigger('click');
        // $('.billing-tab a').trigger('click');

        $('#address_country').chosen({
            search_contains: true,
            width: '99%'
        });

        $('.cc-number').payment('formatCardNumber');
        $('.cc-exp').payment('formatCardExpiry');
        $('.cc-cvc').payment('formatCardCVC');

        $('.cc-number').on('keypress', function(e) {
            var cardType = $.payment.cardType($('.cc-number').val());
            $('.cc-brand').html('<i class="fa fa-lg ' + (cardType ? 'fa-cc-' + cardType : 'fa-credit-card') + '"></i>');
        });

        $.fn.toggleInputError = function(desc, erred) {
            this.parents('.form-group').toggleClass('has-error', erred);

            if (erred) {
                $('#modal-billing .validation').append($('<li>', {
                    'text': desc
                }));
            }

            return this;
        };

        $('#modal-billing .save-details').click(function(e) {
            e.preventDefault();

            $(this).button('loading');

            $('#modal-billing .validation li').remove();

            var cardType = $.payment.cardType($('.cc-number').val());
            $('.cc-number').toggleInputError('Card Number is not valid', !$.payment.validateCardNumber($('.cc-number').val()));
            $('.cc-exp').toggleInputError('Expiration Date is not valid', !$.payment.validateCardExpiry($('.cc-exp').payment('cardExpiryVal')));
            $('.cc-cvc').toggleInputError('Credit Card CCV is not valid', !$.payment.validateCardCVC($('.cc-cvc').val(), cardType));
            $('.cc-name').toggleInputError('Empty or incomplete Name, Please enter full name', !validateFullName($('.cc-name').val()));

            $('#address_line1').toggleInputError('Empty Billing Address', !validateNonEmpty($('#address_line1').val()));
            $('#address_city').toggleInputError('Empty Billing City', !validateNonEmpty($('#address_city').val()));
            $('#address_state').toggleInputError('Empty Billing State/Province', !validateNonEmpty($('#address_state').val()));
            $('#address_zip').toggleInputError('Empty ZIP/Postale code', !validateNonEmpty($('#address_zip').val()));
            $('#address_country').toggleInputError('Country not selected', !validateNonEmpty($('#address_country').val()));

            var formValid = $('#modal-billing .has-error').length === 0;

            $('#modal-billing .validation').toggle(!formValid);

            if (formValid) {
                Stripe.card.createToken(getStripeData(), stripeResponseHandler);
            } else {
                $(this).button('reset');
            }

        });

    });

    $.ajaxSetup({
        beforeSend: function(xhr, settings) {
            var csrftoken = Cookies.get('csrftoken');

            if (csrftoken && !csrfSafeMethod(settings.type) && !this.crossDomain) {
                xhr.setRequestHeader("X-CSRFToken", csrftoken);
            }
        }
    });

    $('.add-cc-btn').click(function(e) {
        e.preventDefault();

        $('.form-group').removeClass('has-error');
        $('#modal-billing .validation li').remove();
        $('#modal-billing .validation').hide();

        $('#modal-billing').modal({
            backdrop: 'static',
            keyboard: false
        });
    });

    $('.start-plan-trial').click(function(e) {
        var btn = $(this);
        var parent = $(this).parents('th');

        swal({
                title: parent.data('plan-title') + " Plan",
                text: "Subscribe to " + parent.data('plan-title') + ' Plan?',
                showCancelButton: true,
                closeOnConfirm: false,
                animation: false,
                showLoaderOnConfirm: true,
                confirmButtonText: "Choose Plan",
                cancelButtonText: "No Thanks"
            },
            function(isConfirmed) {
                if (isConfirmed) {
                    $.ajax({
                        url: config.subscription_trial,
                        type: 'POST',
                        data: {
                            plan: parent.data('plan')
                        },
                        success: function(data) {
                            toastr.success("Your Subscription has been updated.", "Start Trial");
                            swal.close();

                            setTimeout(function() {
                                window.location.reload();
                            }, 1500);
                        },
                        error: function(data) {
                            displayAjaxError('Billing Details', data);
                        }
                    });
                }
            }
        );
    });

    function selectPlan(plan) {
        $.ajax({
            url: config.subscription_plan,
            type: 'POST',
            data: {
                plan: plan
            },
            success: function(data) {
                toastr.success("Your Subscription has been updated.", "Plan Subscription");
                swal.close();

                setTimeout(function() {
                    window.location.href = '/user/profile#plan';
                    window.location.reload();
                }, 1500);
            },
            error: function(data) {
                displayAjaxError('Plan Subscription', data);
            }
        });
    }

    $('.choose-plan').click(function(e) {
        var parent = $(this).parents('.subsciption-plan');
        var plan = parent.data('data-plan');

        if (!window.skipPlanSelectConfirmation) {
            swal({
                    title: parent.data('plan-title') + " Plan",
                    text: "Subscribe to " + parent.data('plan-title') + ' Plan?',
                    showCancelButton: true,
                    closeOnConfirm: false,
                    animation: false,
                    showLoaderOnConfirm: true,
                    confirmButtonText: "Choose Plan",
                    cancelButtonText: "No Thanks"
                },
                function(isConfirmed) {
                    if (isConfirmed) {
                        selectPlan(parent.data('plan'));
                    }
                }
            );
        } else {
            selectPlan(parent.data('plan'));
        }
    });

    $('.choose-shopify-plan').click(function(e) {
        var parent = $(this).parents('.subsciption-plan');
        var plan = parent.data('data-plan');

        $.ajax({
            url: config.shopify_plan,
            type: 'POST',
            data: {
                plan: parent.data('plan')
            },
            success: function(data) {
                setTimeout(function() {
                    if (data.location) {
                        window.location.href = data.location;
                    } else {
                        window.location.reload();
                    }
                }, 500);
            },
            error: function(data) {
                displayAjaxError('Plan Subscription', data);
            }
        });
    });

    $('#modal-subscription-cancel .confirm-cancel-btn').click(function(e) {
        var parent = $(this).parents('.subsciption-plan');
        var plan = parent.data('data-plan');

        $(this).button('loading');

        var subscription_type = $('#modal-subscription-cancel').data('subscription-type');

        if ( subscription_type=="custom" ){
            ajax_url = config.custom_subscription_cancel;
        }
        else {
            ajax_url = config.subscription_cancel;
        }

        $.ajax({
            url: ajax_url,
            type: 'POST',
            data: {
                subscription: $('#modal-subscription-cancel').data('subscription'),
                subscription_type: $('#modal-subscription-cancel').data('subscription-type'),
                when: 'period_end'
            },
            success: function(data) {
                toastr.success("Your Subscription has been canceled.", "Cancel Subscription");
                $('#modal-subscription-cancel').modal('hide');

                setTimeout(function() {
                    window.location.reload();
                }, 1500);
            },
            error: function(data) {
                displayAjaxError('Cancel Subscription', data);
            }
        });
    });

    $('#modal-subscription-cancel-callflex .confirm-cancel-btn').click(function(e) {
        var parent = $(this).parents('.subsciption-plan');
        var plan = parent.data('data-plan');

        $(this).button('loading');

        var subscription_type = $('#modal-subscription-cancel-callflex').data('subscription-type');

        if (subscription_type == "custom"){
            ajax_url = config.custom_subscription_cancel;
        }
        else {
            ajax_url = config.subscription_cancel;
        }

        $.ajax({
            url: ajax_url,
            type: 'POST',
            data: {
                subscription: $('#modal-subscription-cancel-callflex').data('subscription'),
                subscription_type: $('#modal-subscription-cancel-callflex').data('subscription-type'),
                when: 'period_end'
            },
            success: function(data) {
                toastr.success("Your Subscription has been canceled.", "Cancel Subscription");
                $('#modal-subscription-cancel-callflex').modal('hide');

                setTimeout(function() {
                    window.location.reload();
                }, 1500);
            },
            error: function(data) {
                displayAjaxError('Cancel Subscription', data);
            }
        });
    });

    $('.delete-cc-btn').click(function(e) {
        var btn = $(this);
        var parent = $(this).parents('th');

        swal({
                title: "Delete Credit Card",
                text: "Are you sure you want to delete your Credit Card information?",
                type: 'warning',
                showCancelButton: true,
                closeOnConfirm: false,
                animation: false,
                showLoaderOnConfirm: true,
                confirmButtonColor: "#DD6B55",
                confirmButtonText: "Yes",
                cancelButtonText: "No"
            },
            function(isConfirmed) {
                if (isConfirmed) {
                    $.ajax({
                        url: config.customer_source_delete,
                        type: 'POST',
                        success: function(data) {
                            toastr.success("Your Credit Card has been Deleted.", "Delete Credit Card");
                            swal.close();

                            setTimeout(function() {
                                window.location.reload();
                            }, 1500);
                        },
                        error: function(data) {
                            displayAjaxError('Delete Credit Card', data);
                        }
                    });
                }
            }
        );
    });

    $('.cancel-sub-btn').click(function(e) {
        $('#modal-subscription-cancel').data('subscription', $(this).data('subscription'));
        $('#modal-subscription-cancel').data('subscription-type', $(this).data('subscription-type'));

        $('#modal-subscription-cancel .plan-name').text($(this).data('plan'));
        $('#modal-subscription-cancel .billing-end').text($(this).data('period-end'));

        if ($(this).data('status') != 'active') {
            $('#modal-subscription-cancel .part-refund').hide();
            $('#modal-subscription-cancel .period-name').text('trial');
        }

        $('#modal-subscription-cancel').modal('show');
    });

    $('.cancel-sub-btn-callflex').click(function(e) {
        $('#modal-subscription-cancel-callflex').data('subscription', $(this).data('subscription'));
        $('#modal-subscription-cancel-callflex').data('subscription-type', $(this).data('subscription-type'));

        $('#modal-subscription-cancel-callflex .plan-name').text($(this).data('plan'));
        $('#modal-subscription-cancel-callflex .billing-end').text($(this).data('period-end'));

        if ($(this).data('status') != 'active') {
            $('#modal-subscription-cancel-callflex .part-refund').hide();
            $('#modal-subscription-cancel-callflex .period-name').text('trial');
        }

        $('#modal-subscription-cancel-callflex').modal('show');
    });

    $('.pause-account').click(function(e) {
        $('#modal-pause-account').data('plan', $(e.target).data('plan'));
        $('#modal-pause-account').modal('show');
    });

    $(".confirm-pause-btn").click(function(e) {
        var plan = $('#modal-pause-account').data('plan');
        var btn = $(e.target);
        btn.button('loading');

        $.ajax({
            url: config.subscription_plan,
            type: 'POST',
            data: {
                plan: plan
            },
            success: function(data) {
                toastr.success("Your account has been paused.", "Pause Account");
                swal.close();

                setTimeout(function() {
                    $('#modal-pause-account').modal('hide');
                    window.location.reload();
                }, 1500);
            },
            error: function(data) {
                btn.button("reset");
                displayAjaxError('Pause Account', data);
            }
        });
    });

    $('.reactivate-sub-btn').click(function(e) {
        var parent = $(e.target).parents('.subsciption-plan');
        var plan = parent.data('data-plan');

        var btn = $(e.target);
        btn.button('loading');

        $.ajax({
            url: config.subscription_activate,
            type: 'POST',
            data: {
                subscription: btn.data('subscription'),
            },
            success: function(data) {
                toastr.success("Your Subscription has been activated.", "Activate Subscription");

                setTimeout(function() {
                    window.location.reload();
                }, 1500);
            },
            error: function(data) {
                displayAjaxError('Activate Subscription', data);
            }
        });
    });

    $('.plan-more-features .more-feature-list-btn').click(function() {
        $('.plan-more-features').hide();
        $('.plan-feature-list').fadeIn();
    });





    $('.choose-callflex-plan').click(function(e) {
        var parent = $(this).parents('.callflex-subsciption-plan');
        var plan = parent.data('data-plan');

        if (!window.skipPlanSelectConfirmation) {
            swal({
                    title: parent.data('plan-title') + " Plan",
                    text: "Subscribe to " + parent.data('plan-title') + ' Plan?',
                    showCancelButton: true,
                    closeOnConfirm: false,
                    animation: false,
                    showLoaderOnConfirm: true,
                    confirmButtonText: "Choose Plan",
                    cancelButtonText: "No Thanks"
                },
                function(isConfirmed) {
                    if (isConfirmed) {
                        selectCallflexPlan(parent.data('plan'));
                    }
                }
            );
        } else {
            selectCallflexPlan(parent.data('plan'));
        }
    });


    function selectCallflexPlan(plan) {
        $.ajax({
            url: config.callflex_subscription,
            type: 'POST',
            data: {
                plan: plan
            },
            success: function(data) {
                toastr.success("Your Subscription has been updated.", "Plan Subscription");
                swal.close();

                setTimeout(function() {
                    // window.location.href = '/user/profile#plan';
                    window.location.reload();
                }, 1500);
            },
            error: function(data) {
                displayAjaxError('Plan Subscription', data);
            }
        });
    }

    $('.shopify-callflex-activate').click(function(e) {

        $.ajax({
            url: config.shopify_callflex_subscription,
            type: 'POST',
            data: {
            },
            success: function(data) {
                setTimeout(function() {
                    if (data.location) {
                        window.location.href = data.location;
                    } else {
                        window.location.reload();
                    }
                }, 500);
            },
            error: function(data) {
                displayAjaxError('CallFlex Subscription', data);
            }
        });
    });


})(config);
