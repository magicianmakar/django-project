function addBaremetricsForm(accessToken, jwtToken) {
    !function(){if(window.barecancel&&window.barecancel.created)window.console&&console.error&&console.error("Barecancel snippet included twice.");else{window.barecancel={created:!0};var a=document.createElement("script");a.src="https://baremetrics-barecancel.baremetrics.com/js/application.js",a.async=!0;var b=document.getElementsByTagName("script")[0];b.parentNode.insertBefore(a,b),

        window.barecancel.params = {
            access_token_id: accessToken,
            token: jwtToken,
            callback_send: function (data) {
                var $triggerBtn = $('#barecancel-trigger');
                $triggerBtn.button('loading');
                var subId = $triggerBtn.data('subscription');

                $.ajax({
                    url: config.subscription_cancel,
                    type: 'POST',
                    data: {
                        subscription: subId,
                        when: 'period_end'
                    },
                    success: function(data) {
                        toastr.success(
                            "Your Subscription has been canceled.",
                            "Cancel Subscription"
                        );
                        setTimeout(function() {
                            window.location.reload();
                        }, 1500);
                    },
                    error: function(data) {
                        displayAjaxError('Cancel Subscription', data);
                    }
                });
            },
            callback_error: function (data) {
                swal('Cancellation Insights', data.message, 'warning');
            },
        };

    }}();
}
