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
                shopifyMessage += 'to authorize an increase in the amount that Dropified can charge your Shopify account';
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

    var billingElem = $('#addon-billing');
    if (btnID == 'addon-install') {
        text = 'You will be charged ' + billingElem.data('billing-title');

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

$('#add-addon-btn').click(function (e) {
    e.preventDefault();

    Swal.fire({
        title: 'Add New Addon',
        input: 'text',
        showCancelButton: true,
        confirmButtonText: 'Add',
        showLoaderOnConfirm: true,
        preConfirm: function preConfirm(title) {
            var formData = new FormData();
            formData.append('title', title);

            return fetch(api_url('add', 'addons'), {method: 'post', body: formData}).then(function (response) {
                if (!response.ok) {
                    throw new Error(response.statusText);
                }

                return response.json();
            }).catch(function (error) {
                Swal.showValidationMessage("Request failed: ".concat(error));
            });
        },
        allowOutsideClick: function allowOutsideClick() {
            return !Swal.isLoading();
        }
    }).then(function (result) {
        if (result.value.id) {
            window.location.href = '/addons/edit/' + result.value.slug;
        }
    });
});

$('#addon-edit-save').click(function (e) {
    e.preventDefault();

    var formData = new FormData();
    formData.append('addon-id', $('#addon-id').val());
    formData.append('addon-title', $('#addon-title').val());
    formData.append('addon-short', $('#addon-short').val());
    formData.append('addon-description', CKEDITOR.instances['addon-description'].getData());
    formData.append('addon-faq', CKEDITOR.instances['addon-faq'].getData());
    formData.append('addon-icon', $('#addon-icon')[0].files[0]);
    formData.append('addon-banner', $('#addon-banner')[0].files[0]);
    formData.append('addon-youtube', $('#addon-youtube').val());
    formData.append('addon-vimeo', $('#addon-vimeo').val());
    formData.append('addon-categories', $('#addon-categories').val());
    formData.append('addon-price', $('#addon-price').val());
    formData.append('addon-trial-days', $('#addon-trial-days').val());
    formData.append('addon-status', $('#addon-status').val());

    [0, 1, 2].forEach(function (i) {
        formData.append('addon-key-title-' + i, $('#addon-key-title-' + i).val());
        formData.append('addon-key-description-' + i, $('#addon-key-description-' + i).val());
        formData.append('addon-key-banner-' + i, $('#addon-key-banner-' + i)[0].files[0]);
    });

    fetch(api_url('edit', 'addons'), {
        method: 'post',
        body: formData
    }).then(function () {
        window.location.reload();
    }, function () {
        Swal.fire('Addon Edit', 'Could not save changes', 'error');
    });
});

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
