function addBaremetricsForm(accessToken, stripeCustomerID, testMode) {
    !function(){if(window.barecancel&&window.barecancel.created)window.console&&console.error&&console.error("Barecancel snippet included twice.");else{window.barecancel={created:!0};var a=document.createElement("script");a.src="https://baremetrics-barecancel.baremetrics.com/js/application.js",a.async=!0;var b=document.getElementsByTagName("script")[0];b.parentNode.insertBefore(a,b),

        window.barecancel.params = {
            access_token_id: accessToken,
            customer_oid: stripeCustomerID,
            test_mode: testMode,
            callback_send: function (data) {
                var $triggerBtn = $('#barecancel-trigger');
                $triggerBtn.button('loading');

                cancelStripeSubscription().done(function(data) {
                    toastr.success(
                        "Your Subscription has been canceled.",
                        "Cancel Subscription"
                    );
                    setTimeout(function() {
                        window.location.reload();
                    }, 1500);
                }).fail(function(data) {
                    displayAjaxError('Cancel Subscription', data);
                });
            },
            callback_error: function(error) {
                window.location.reload();
            }
        };
    }}();
}
