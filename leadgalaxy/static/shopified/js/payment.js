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
                    toastr.success("Billing Details has been updated.", "Billing Details");
                    $('#modal-billing').modal('hide');

                    setTimeout(function() {
                        window.location.reload();
                    }, 1000);
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
                text: "Start the " + parent.data('trial-days') + ' days trial?',
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

    $('.choose-plan').click(function(e) {
        var parent = $(this).parents('.subsciption-plan');
        var plan = parent.data('data-plan');

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
                        url: config.subscription_plan,
                        type: 'POST',
                        data: {
                            plan: parent.data('plan')
                        },
                        success: function(data) {
                            toastr.success("Your Subscription has been updated.", "Plan Subscription");
                            swal.close();

                            setTimeout(function() {
                                window.location.reload();
                            }, 1500);
                        },
                        error: function(data) {
                            displayAjaxError('Plan Subscription', data);
                        }
                    });
                }
            }
        );
    });

    $('.cancel-sub-btn').click(function() {
        $('#modal-subscribtion-cancel').data('subscription', $(this).data('subscription'));
        $('#modal-subscribtion-cancel .plan-name').text($(this).data('plan'));
        $('#modal-subscribtion-cancel .billing-end').text($(this).data('period-end'));
        $('#modal-subscribtion-cancel').modal('show');
    });

    $('.plan-more-features .more-feature-list-btn').click(function() {
        $('.plan-more-features').hide();
        $('.plan-feature-list').fadeIn();
    });

})(config);