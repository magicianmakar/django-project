$.fn.bootstrapBtn = $.fn.button.noConflict();
$.fn.bootstrapTooltip = $.fn.tooltip.noConflict();

function changeAddonSubscription(btn) {
    var endpoint = btn.data('endpoint');
    btn.bootstrapBtn('loading');

    $.ajax({
        url: api_url(endpoint.target, 'addons'),
        type: 'POST',
        data: {
            billing: $('#addon-billing').data('billing'),
            addon: btn.data('addon')
        }
    }).done(function (data) {
        if (data.shopify) {
            var shopifyMessage = 'To install this Addon please click Continue ';
            var shopifyTitle;
            var nextUrl;
            if (data.shopify.limit_exceeded_link) {
                // shopifyMessage += 'to authorize an increase in the amount that Dropified can charge your Shopify account';
                shopifyMessage = 'Dropified will need to increase the amount it can charge for your ';
                shopifyMessage += 'subscription before installing, from ' + data.shopify.from + ' to ';
                shopifyMessage += data.shopify.to + '. Do you accept?';
                shopifyTitle = 'Shopify Limit Exceeded';
                nextUrl = data.shopify.limit_exceeded_link;
            } else if (data.shopify.confirmation_url) {
                shopifyMessage += 'to authorize an extra subscription for your addons';
                shopifyTitle = 'Shopify Extra Subscription Needed';
                nextUrl = data.shopify.confirmation_url;
            } else if (data.shopify.installation_url) {
                shopifyMessage += 'to install Dropified in your Shopify account';
                shopifyTitle = 'Shopify Installation Missing';
                nextUrl = data.shopify.installation_url;
            }
            Swal.fire({
                title: shopifyTitle,
                text: shopifyMessage,
                showCancelButton: true,
                confirmButtonColor: '#3085d6',
                cancelButtonColor: '#d33',
                confirmButtonText: 'Continue',
            }).then(function(result) {
                if (result.value) {
                    window.open(nextUrl);
                }
                window.location.reload();
            });
        } else {
            window.location.reload();
        }
    }).fail(function (data) {
        displayAjaxError(endpoint.name, data);
        btn.bootstrapBtn('reset');
    });
}

$('#active-until a').on('click', function(e) {
    changeAddonSubscription($('#addon-reinstall'));
});

$('.addon-install, .addon-uninstall').click(function (e) {
    var btn = $(e.currentTarget);
    var btnID = e.target.id;
    var text = '';

    var billingElem = $('#addon-billing');
    if (btnID == 'addon-install') {
        var addonStoreLength = $('.addon-supported-platforms span').length;
        if (addonStoreLength > 0 && addonStoreLength < 5) {
            text = '<div class="m-b-sm">' + $('.addon-supported-platforms').html().trim() + '</div>';
        }
        text += 'You will be charged ' + billingElem.data('billing-title');

        var trialDays = billingElem.data('trial-days');
        if (trialDays) {
            text += ' after ' + trialDays + '-Day Free Trial for this Addon.';
        }

        text += ' Would you like to continue?';
    } else if (btnID == 'addon-uninstall') {
        text = 'Are you sure you want to Uninstall?';
    } else if (btnID == 'addon-reinstall') {
        changeAddonSubscription(btn);
        return;
    }
    Swal.fire({
        title: btn.data("title"),
        text: text,
        html: text,
        showCancelButton: true,
        confirmButtonColor: '#3085d6',
        cancelButtonColor: '#d33',
        confirmButtonText: 'Continue',
    }).then(function(result) {
        if(result.value) {
            changeAddonSubscription(btn);
        }
    });
});

function setTrialDays(trialDays) {
    if (!$('#free-trial').length) {
        return;
    }

    if (trialDays) {
        $('#free-trial').removeClass('hidden').find('span').text(trialDays);
    } else {
        $('#free-trial').addClass('hidden');
    }
}
setTrialDays($('#addon-billing').data('trial-days'));

if ($(window).width() <=1024 ) {
    var e = $('iframe.addon-videos');
    w = parseInt(e.parent().width());

    // Width to Height Ratio of Responsive Youtube videos is usually 1.77
    h = Math.ceil(w/1.77);
    e.width(w);
    e.height(h);
}

// Display Navbar search box with 500 mili sec delay
$('.search-icon').on('click', function(e) {
    e.preventDefault();

    if ($(this).hasClass('fa-search')) {
        $('#nav-addon-search').show(500);
      }
    else {
        $('#nav-addon-search').hide(500);
    }

    $(this).toggleClass('fa-search');
    $(this).toggleClass('fa-times');
    $(this).toggleClass('search-icon');
    $(this).toggleClass('close-icon');
});

$('#addon-categories').chosen();
