window.Currency = {
    storeFormat: config.currencyFormat,
    formatTypes: {
        decimals: {
            without: function(value) {
                // Only uses if no_decimals on format
                return value.toFixed(0);
            },
            default: function(value) {
                // Uses if there is no decimals definition on format
                return value.toFixed(2);
            }
        },
        separator: {
            default: function(value) {
                // No separator is defined
                return value.replace(/(\d)(?=(\d{3})+(?:\.\d+)?$)/g, '$1,');
            },
            comma: function(value) {
                // For when comma_separator is present on format
                var separatedValue = value.replace(/(\d)(?=(\d{3})+(?:\.\d+)?$)/g, '$1.');
                return separatedValue.replace(/\.(\d{1,2})?$/, ',$1');
            },
            space: function(value) {
                // For when space_separator is present on format
                var separatedValue = value.replace(/(\d)(?=(\d{3})+(?:\.\d+)?$)/g, '$1 ');
                return separatedValue.replace(/\.(\d{1,2})?$/, ',$1');
            },
            apostrophe: function(value) {
                // For when apostrophe_separator is present on format
                return value.replace(/(\d)(?=(\d{3})+(?:\.\d+)?$)/g, '$1\'');
            }
        }
    },
    decimalsFormat: function(baseValue) {
        return window.Currency.formatTypes.decimals.default(baseValue);
    },
    separatorFormat: function(baseValue) {
        return window.Currency.formatTypes.separator.default(baseValue);
    },
    defineFormat: function(newFormat) {
        if (newFormat.trim() == '') {
            // Setting default format if empty
            newFormat = '${{ amount }}';
        }
        window.Currency.storeFormat = newFormat;

        if (window.Currency.storeFormat.indexOf('no_decimals') > -1) {
            window.Currency.decimalsFormat = window.Currency.formatTypes.decimals.without;
        } else {
            window.Currency.decimalsFormat = window.Currency.formatTypes.decimals.default;
        }

        if (window.Currency.storeFormat.indexOf('comma_separator') > -1) {
            window.Currency.separatorFormat = window.Currency.formatTypes.separator.comma;
        } else if (window.Currency.storeFormat.indexOf('space_separator') > -1) {
            window.Currency.separatorFormat = window.Currency.formatTypes.separator.space;
        } else if (window.Currency.storeFormat.indexOf('apostrophe_separator') > -1) {
            window.Currency.separatorFormat = window.Currency.formatTypes.separator.apostrophe;
        } else {
            window.Currency.separatorFormat = window.Currency.formatTypes.separator.default;
        }
    },
    format: function(baseValue, noSign) {
        var decimalsValue = window.Currency.decimalsFormat(baseValue),
            value = window.Currency.separatorFormat(decimalsValue);

        if (noSign) {
            return value;
        } else {
            return window.Currency.storeFormat.replace(/(\{\{ ?\S+ ?\}\})/, value);
        }
    }
};


(function(d, s, id) {
    var js, fjs = d.getElementsByTagName(s)[0];
    if (d.getElementById(id)) return;
    js = d.createElement(s); js.id = id;
    js.src = "//connect.facebook.net/en_US/sdk.js";
    fjs.parentNode.insertBefore(js, fjs);
}(document, 'script', 'facebook-jssdk'));

window.fbAsyncInit = function() {
    FB.init({
        appId      : config.facebook.appId,
        cookie     : true,  // enable cookies to allow the server to access the session
        xfbml      : true,  // parse social plugins on this page
        version    : 'v2.8' // use graph api version 2.8
    });

    FB.getLoginStatus(function(response) {
        window.ProfitDashboard.statusChangeCallback(response);
    });

    FB.Event.subscribe('auth.logout', window.ProfitDashboard.facebookStatus.connect);
}

window.ProfitDashboard = {
    start: null,
    count: 0,
    firstTime: true,
    totalsProfitAmount: parseFloat($('#totals-profit').attr('data-original-amount')),
    totalsOtherCostsAmount: parseFloat($('#totals-other-costs').attr('data-original-amount')),
    totalsTotalCostsAmount: parseFloat($('#totals-total-costs').attr('data-original-amount')),
    otherCostsAjaxTimeout: {},
    init: function() {
        this.initTooltip();
        this.initDatepicker();
        this.initExpandable();

        this.fixStripes();

        this.onClickOpenDates();
        this.onClickCloseDates();
        this.onFacebookSyncFormSubmit();
        this.onOtherCostsChange();

        this.facebookStatus.connect();

        this.checkCalculationPusher();
    },
    initTooltip: function() {
        $('[data-toggle="profit-tooltip"]').tooltip();
    },
    initDatepicker: function() {
        $('#profit-range .input-daterange').datepicker({
            keyboardNavigation: false,
            forceParse: false,
            autoclose: true
        });
    },
    initExpandable: function() {
        $('#profits tbody tr').each(function() {
            if ($(this).hasClass('empty')) {
                if (window.ProfitDashboard.start == null) {
                    window.ProfitDashboard.start = $(this);
                } else {
                    $(this).css('display', 'none');
                    window.ProfitDashboard.count += 1;
                }
            }

            if (!$(this).next().hasClass('empty')) {
                if (window.ProfitDashboard.count > 0) {
                    var startDate = window.ProfitDashboard.start.find('td:first');
                    window.ProfitDashboard.start.attr('data-initial-text', startDate.text()).addClass('closed');
                    startDate.text(startDate.text() + ' - ' + $(this).find('td:first').text());
                    window.ProfitDashboard.start.find('.actions').append($('<a href="#" class="open-dates"><i class="glyphicon glyphicon-chevron-down">'));
                    window.ProfitDashboard.start.tooltip('destroy');
                }
                window.ProfitDashboard.start = null;
                window.ProfitDashboard.count = 0;
            }
        });
    },
    reloadExpandable: function() {
        $('.open-dates, .close-dates', '#profits tbody tr').remove();
        $('.opened, .closed', '#profits tbody').removeClass('opened closed');
        $('#profits tbody tr').each(function() {
            $(this).css('display', '').find('td:first').text($(this).attr('data-initial-text'));
        });

        window.ProfitDashboard.initExpandable();
    },
    facebookStatus: {
        connect: function() {
            $('#connect-facebook').css('display', '');
            $('#loading-facebook').css('display', 'none');
            $('#facebook-logged-in').css('display', 'none');
        },
        loading: function() {
            $('#loading-facebook').css('display', '');
            $('#connect-facebook').css('display', 'none');
            $('#facebook-logged-in').css('display', 'none');
        },
        loggedIn: function() {
            $('#facebook-logged-in').css('display', '');
            $('#connect-facebook').css('display', 'none');
            $('#loading-facebook').css('display', 'none');
        }
    },
    fixStripes: function() {
        $('#profits tbody tr.odd').removeClass('odd');
        var odd = false;
        $('#profits tbody tr:visible').each(function() {
            if (odd) {
                $(this).addClass('odd');
                odd = false;
            } else {
                odd = true;
            }
        });
    },
    onClickOpenDates: function() {
        $('#profits').on('click', 'tr .actions a.open-dates', function(e) {
            e.preventDefault();

            var selectedRow = $(this).parents('.profit');

            selectedRow.find('td:first').text(selectedRow.attr('data-initial-text'));
            selectedRow.tooltip();

            var nextRows = selectedRow.nextAll(),
                index = nextRows.index(nextRows.nextAll(':not(.empty):first'));
            nextRows.filter(':first').css('display', '');
            nextRows.nextAll(':lt(' + index + ')').css('display', '');

            $(this).find('.glyphicon').removeClass('glyphicon-chevron-down').addClass('glyphicon-chevron-up');
            $(this).removeClass('open-dates').addClass('close-dates');

            selectedRow.addClass('opened').removeClass('closed');
            window.ProfitDashboard.fixStripes();
        });
    },
    onClickCloseDates: function() {
        $('#profits').on('click', 'tr .actions a.close-dates', function(e) {
            e.preventDefault();

            var selectedRow = $(this).parents('.profit'),
                nextRows = selectedRow.nextAll(),
                index = nextRows.index(nextRows.filter(':not(.empty):first'));

            selectedRow.tooltip('destroy');
            selectedRow.addClass('closed').removeClass('opened');

            if (nextRows.filter(':not(.empty):first').length == 0) {
                var index = nextRows.index(nextRows.filter(':last')) + 1;
            }
            
            selectedRow = nextRows.filter(':lt(' + index + ')').css('display', 'none').filter(':last');
            var dateColumn = $(this).parents('.profit').find('td:first');
            dateColumn.text(dateColumn.text() + ' - ' + selectedRow.find('td:first').text());

            $(this).find('.glyphicon').removeClass('glyphicon-chevron-up').addClass('glyphicon-chevron-down');
            $(this).removeClass('close-dates').addClass('open-dates');

            window.ProfitDashboard.fixStripes();
        });
    },
    onFacebookSyncFormSubmit: function() {
        $('#facebook-sync').on('submit', function(e) {
            e.preventDefault();

            window.ProfitDashboard.facebookStatus.loading();
            $.ajax({
                type: $(this).attr('method'),
                url: $(this).attr('action'),
                data: $(this).serialize(),
                dataType: 'json',
                success: function(result) {
                    if (result.success) {
                        window.ProfitDashboard.facebookInsightsPusherNotification();
                    }
                }
            });
        });
    },
    statusChangeCallback: function(response) {
        // The response object is returned with a status field that lets the
        // app know the current login status of the person.
        // Full docs on the response object can be found in the documentation
        // for FB.getLoginStatus().
        if (response.status === 'connected' && !window.ProfitDashboard.firstTime) {
            window.ProfitDashboard.facebookStatus.loading();
            $.ajax({
                type: 'post',
                url: '/profit-dashboard/facebook/insights',
                data: {'access_token': response.authResponse.accessToken},
                dataType: 'json',
                success: function(result) {
                    if (result.success) {
                        window.ProfitDashboard.facebookInsightsPusherNotification();
                    }
                }
            });
        } else {
            if (response.authResponse) {
                window.ProfitDashboard.facebookStatus.loggedIn();
                $('input[name="access_token"]').val(response.authResponse.accessToken);
            } else {
                window.ProfitDashboard.facebookStatus.connect();
            }
        }
        window.ProfitDashboard.firstTime = false;
        $('#facebook-insights').css('display', '');
    },
    checkLoginState: function() {
        FB.getLoginStatus(function(response) {
            window.ProfitDashboard.statusChangeCallback(response);
        });
    },
    facebookInsightsPusherNotification: function() {
        var pusher = new Pusher(config.sub_conf.key);
        var channel = pusher.subscribe(config.sub_conf.channel);

        channel.bind('facebook-insights', function(data) {
            if (data.success) {
                setTimeout(function() {
                    window.ProfitDashboard.facebookStatus.loggedIn();
                    window.location.reload();
                }, 1000);
            } else {
                displayAjaxError('Facebook Insights', data);
                window.ProfitDashboard.facebookStatus.loggedIn();
                $('#last-synced').text('Error');
            }
        });
    },
    checkCalculationPusher: function() {
        if (config.runningCalculation) {
            var pusher = new Pusher(config.sub_conf.key);
            var channel = pusher.subscribe(config.sub_conf.channel);

            channel.bind('profit-calculations', function(data) {
                if (data.success) {
                    window.ProfitDashboard.reloadTable();
                } else {
                    displayAjaxError(
                        'Profit Calculations',
                        'There was an error calculating your profits, reload the page or contact our support for further assistance'
                    );
                }
            });
        }
    },
    reloadTable: function() {
        var endDate = $('#profits tbody tr:first').attr('id').replace(/date\-(\d{2}).?(\d{2}).?(\d{4})$/, '$1/$2/$3'),
            startDate = $('#profits tbody tr:last').attr('id').replace(/date\-(\d{2}).?(\d{2}).?(\d{4})$/, '$1/$2/$3');
        $.ajax({
            type: 'get',
            url: '/profit-dashboard/profits',
            data: {start: startDate, end: endDate},
            dataType: 'json',
            success: function(result) {
                $('#profits tbody tr').remove();

                for (var i = 0, iLength = result.profits.length; i < iLength; i++) {
                    var profitRow = Handlebars.compile($("#profit").html()),
                        profit = result.profits[i],
                        profitData = $.extend({}, profit, {
                            'currency_sign': config.currencySign,
                            'other_costs_url': config.profitOtherCostsAjaxUrl
                        });

                    profitData['item'] = $.extend({}, profitData['item'], {
                        'currency_revenue': window.Currency.format(profit.item.revenue),
                        'currency_fulfillment_cost': window.Currency.format(profit.item.fulfillment_cost),
                        'currency_ad_spend': window.Currency.format(profit.item.ad_spend),
                        'currency_outcome': window.Currency.format(profit.item.outcome, true),
                        'currency_profit': window.Currency.format(profit.item.profit, true),
                        'other_costs': profit.item.other_costs.toFixed(2)
                    });

                    $('#profits tbody').append(profitRow({'profit': profitData}));
                }

                window.ProfitDashboard.reloadExpandable();
                window.ProfitDashboard.fixStripes();
            }
        });
    },
    onOtherCostsChange: function() {
        $('#profits').on('submit', 'tr .other-costs-form', function(e) {
            e.preventDefault();
        });

        $('#profits').on('keyup', 'tr [name="other_costs"]', function(e) {
            if (isNaN(String.fromCharCode(e.which)) && !(e.which == 8 || e.which == 46)) {
                return;
            }

            var otherCosts = $(this).parents('.other-costs'),
                originalValue = parseFloat(otherCosts.attr('data-original-amount')),
                inputValue = parseFloat($(this).val()),
                totalCosts = otherCosts.parent().find('.total-costs span'),
                profitAmont = otherCosts.parent().find('.profit-amount span'),
                totalCostsValue = parseFloat(totalCosts.attr('data-original-amount')),
                profitAmontValue = parseFloat(profitAmont.attr('data-original-amount')),
                revenue = parseFloat(otherCosts.parent().find('.revenue').attr('data-original-amount')),
                percentage = otherCosts.parent().find('.percentage');

            if (isNaN(inputValue)) {
                inputValue = 0;
            }

            value = inputValue - originalValue;
            totalCosts.text((totalCostsValue + value).toFixed(2));
            profitAmont.text((profitAmontValue - value).toFixed(2));
            console.log(profitAmontValue, '-', inputValue, '=', (profitAmontValue - inputValue), revenue);
            var percentageAmount = parseInt((profitAmontValue - inputValue) / revenue * 100);
            if (isNaN(percentageAmount)) {
                percentageAmount = 0;
            }
            percentage.text(percentageAmount + '%');

            otherCosts.attr('data-original-amount', inputValue.toFixed(2));
            totalCosts.attr('data-original-amount', (totalCostsValue + value).toFixed(2));
            profitAmont.attr('data-original-amount', (profitAmontValue - value).toFixed(2));

            window.ProfitDashboard.totalsProfitAmount -= value;
            window.ProfitDashboard.totalsOtherCostsAmount += value;
            window.ProfitDashboard.totalsTotalCostsAmount += value;
            $('#totals-profit').text(window.ProfitDashboard.totalsProfitAmount.toFixed(2));
            $('#totals-other-costs').text(window.ProfitDashboard.totalsOtherCostsAmount.toFixed(2));
            $('#totals-total-costs').text(window.ProfitDashboard.totalsTotalCostsAmount.toFixed(2));

            if (($(this).parents('tr').hasClass('empty') && inputValue != 0)) {
                $(this).parents('tr').removeClass('empty');
                window.ProfitDashboard.reloadExpandable();
                window.ProfitDashboard.fixStripes();
            }

            $(this).off('blur');
            if (!$(this).parents('tr').hasClass('empty') && inputValue == 0) {
                $(this).one('blur', function() {
                    $(this).parents('tr').addClass('empty');
                    window.ProfitDashboard.reloadExpandable();
                    window.ProfitDashboard.fixStripes();
                });
            }

            window.ProfitDashboard.saveOtherCost($(this), inputValue, value);
        });
    },
    saveOtherCost: function(otherCostsInput, amount) {
        var form = otherCostsInput.parents('.other-costs-form'),
            tr = otherCostsInput.parents('tr'),
            trId = tr.attr('id');

        clearTimeout(window.ProfitDashboard.otherCostsAjaxTimeout[trId]);
        window.ProfitDashboard.otherCostsAjaxTimeout[trId] = setTimeout(function() {
            $.ajax({
                url: form.attr('action'),
                type: 'POST',
                data: {
                    amount: amount,
                    date: trId.replace('date-', '')
                },
                context: {
                    otherCostsInput: otherCostsInput,
                    form: form
                },
                beforeSend: function() {
                    form.find('.loading').removeClass('hidden');
                },
                success: function (data) {
                    if (!data.status == 'ok') {
                        displayAjaxError('Other Costs save', data);
                    }
                },
                error: function (data) {
                    displayAjaxError('Other Costs save', data);
                },
                complete: function() {
                    form.find('.loading').addClass('hidden');
                }
            });
        }, 2000);
    }
};

window.ProfitDashboard.init();
