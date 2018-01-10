var Currency = {
    storeFormat: config.currencyFormat,
    init: function() {
        if (!this.storeFormat) {
            this.storeFormat = '';
        }
        this.defineFormat(this.storeFormat);
    },
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
        return this.formatTypes.decimals.default(baseValue);
    },
    separatorFormat: function(baseValue) {
        return this.formatTypes.separator.default(baseValue);
    },
    defineFormat: function(newFormat) {
        if (newFormat.trim() == '') {
            // Setting default format if empty
            newFormat = '${{ amount }}';
        }
        this.storeFormat = newFormat;

        if (this.storeFormat.indexOf('no_decimals') > -1) {
            this.decimalsFormat = this.formatTypes.decimals.without;
        } else {
            this.decimalsFormat = this.formatTypes.decimals.default;
        }

        if (this.storeFormat.indexOf('comma_separator') > -1) {
            this.separatorFormat = this.formatTypes.separator.comma;
        } else if (this.storeFormat.indexOf('space_separator') > -1) {
            this.separatorFormat = this.formatTypes.separator.space;
        } else if (this.storeFormat.indexOf('apostrophe_separator') > -1) {
            this.separatorFormat = this.formatTypes.separator.apostrophe;
        } else {
            this.separatorFormat = this.formatTypes.separator.default;
        }
    },
    format: function(baseValue, noSign) {
        var decimalsValue = this.decimalsFormat(baseValue),
            value = this.separatorFormat(decimalsValue);

        if (noSign) {
            return value;
        } else {
            return this.storeFormat.replace(/(\{\{ ?\S+ ?\}\})/, value);
        }
    }
};

Currency.init();


// Profit JS
(function() {
    var ProfitDashboard = {
        profitsData: profitsData,
        start: null,
        count: 0,
        totalsProfitAmount: parseFloat($('#totals-profit').attr('data-original-amount')),
        totalsOtherCostsAmount: parseFloat($('#totals-other-costs').attr('data-original-amount')),
        totalsTotalCostsAmount: parseFloat($('#totals-total-costs').attr('data-original-amount')),
        otherCostsAjaxTimeout: {},
        chartsData: {},
        chartsLabels: [],
        profitChart: null,
        profitChartData: null,
        chartTime: 'daily',  // daily, weekly, monthly
        min_months_for_weekly_chart: 4,
        min_months_for_daily_chart: 2,
        init: function() {
            this.initTooltip();
            this.initDatepicker();
            this.initExpandable();

            this.fixStripes();
            this.initializeChartsData();
            this.loadCharts();

            this.onClickOpenDates();
            this.onClickCloseDates();
            this.onOtherCostsChange();
            this.onGraphViewClick();
            this.onTabsChange();
            this.onChartToggleDataClick();

            if (window.location.hash) {
                $('#top-controls-menu a[href="' + window.location.hash + '"]').trigger('click');
            }
        },
        initTooltip: function() {
            $('[data-toggle="profit-tooltip"]').tooltip();
        },
        initDatepicker: function() {
            $('#profit-range .input-daterange').datepicker({
                keyboardNavigation: false,
                forceParse: false,
                autoclose: true,
                startDate: moment().subtract(35, 'days').format('MM/DD/YYYY')
            });
        },
        initExpandable: function() {
            $('#profits tbody tr').each(function() {
                if ($(this).hasClass('empty')) {
                    if (ProfitDashboard.start == null) {
                        ProfitDashboard.start = $(this);
                    } else {
                        $(this).css('display', 'none');
                        ProfitDashboard.count += 1;
                    }
                }

                if (!$(this).next().hasClass('empty')) {
                    if (ProfitDashboard.count > 0) {
                        var startDate = ProfitDashboard.start.find('td:first');
                        ProfitDashboard.start.attr('data-initial-text', startDate.text()).addClass('closed');
                        startDate.text(startDate.text() + ' - ' + $(this).find('td:first').text());
                        ProfitDashboard.start.find('.actions').append($('<a href="#" class="open-dates"><i class="glyphicon glyphicon-chevron-down">'));
                        ProfitDashboard.start.tooltip('destroy');
                    }
                    ProfitDashboard.start = null;
                    ProfitDashboard.count = 0;
                }
            });
        },
        reloadExpandable: function() {
            $('.open-dates, .close-dates', '#profits tbody tr').remove();
            $('.opened, .closed', '#profits tbody').removeClass('opened closed');
            $('#profits tbody tr').each(function() {
                $(this).css('display', '').find('td:first').text($(this).attr('data-initial-text'));
            });

            ProfitDashboard.initExpandable();
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
                ProfitDashboard.fixStripes();
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

                ProfitDashboard.fixStripes();
            });
        },
        hideDataGenerationLoading: function() {
            $('#loading-data').css('display', 'none');
            $('#profit-data').css('display', '');
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
                var percentageAmount = parseInt((profitAmontValue - inputValue) / revenue * 100);
                if (isNaN(percentageAmount)) {
                    percentageAmount = 0;
                }
                percentage.text(percentageAmount + '%');

                otherCosts.attr('data-original-amount', inputValue.toFixed(2));
                totalCosts.attr('data-original-amount', (totalCostsValue + value).toFixed(2));
                profitAmont.attr('data-original-amount', (profitAmontValue - value).toFixed(2));

                ProfitDashboard.totalsProfitAmount -= value;
                ProfitDashboard.totalsOtherCostsAmount += value;
                ProfitDashboard.totalsTotalCostsAmount += value;
                $('#totals-profit').text(Currency.format(ProfitDashboard.totalsProfitAmount, true));
                $('#totals-other-costs').text(Currency.format(ProfitDashboard.totalsOtherCostsAmount, true));
                $('#totals-total-costs').text(Currency.format(ProfitDashboard.totalsTotalCostsAmount, true));

                if (($(this).parents('tr').hasClass('empty') && inputValue != 0)) {
                    $(this).parents('tr').removeClass('empty');
                    ProfitDashboard.reloadExpandable();
                    ProfitDashboard.fixStripes();
                }

                $(this).off('blur');
                if (!$(this).parents('tr').hasClass('empty') && inputValue == 0) {
                    $(this).one('blur', function() {
                        $(this).parents('tr').addClass('empty');
                        ProfitDashboard.reloadExpandable();
                        ProfitDashboard.fixStripes();
                    });
                }

                ProfitDashboard.saveOtherCost($(this), inputValue, value);
            });
        },
        saveOtherCost: function(otherCostsInput, amount) {
            var form = otherCostsInput.parents('.other-costs-form'),
                tr = otherCostsInput.parents('tr'),
                trId = tr.attr('id');

            clearTimeout(ProfitDashboard.otherCostsAjaxTimeout[trId]);
            ProfitDashboard.otherCostsAjaxTimeout[trId] = setTimeout(function() {
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
        },
        loadChartsData: function() {
            var results = {revenue: [], fulfillment_cost: [], ads_spend: [], other_costs: [], total_costs: []},
                activeGraphViewCssClass = '.' + this.chartTime;

            if (this.chartTime == 'daily') {
                for (var iLength = this.profitsData.length, i = 0; i <= iLength; i++) {
                    var profit = this.profitsData[i];
                    if (!profit) {
                        continue;
                    }

                    results.revenue.push(+profit.revenue.toFixed(2));
                    results.fulfillment_cost.push(+profit.fulfillment_cost.toFixed(2));
                    results.ads_spend.push(+profit.ad_spend.toFixed(2));
                    results.other_costs.push(+profit.other_costs.toFixed(2));
                    var total_costs = profit.fulfillment_cost + profit.ad_spend + profit.other_costs;
                    results.total_costs.push(+total_costs.toFixed(2));
                }
            } else if (this.chartTime == 'weekly') {
                var position = 0,
                    nextMonday = moment(this.profitsData[0].date_as_string.replace(/(\d{2}).?(\d{2}).?(\d{4})$/, '$3-$1-$2'));

                results.revenue[position] = 0.0;
                results.fulfillment_cost[position] = 0.0;
                results.ads_spend[position] = 0.0;
                results.other_costs[position] = 0.0;
                results.total_costs[position] = 0.0;
                for (var iLength = this.profitsData.length, i = 0; i <= iLength; i++) {
                    var profit = this.profitsData[i];
                    if (!profit) {
                        continue;
                    }

                    var profitDate = moment(profit.date_as_string.replace(/(\d{2}).?(\d{2}).?(\d{4})$/, '$3-$1-$2'))
                    if (profitDate.isAfter(nextMonday)) {
                        position += 1;
                        nextMonday = nextMonday.add(1, 'weeks');

                        results.revenue[position] = 0.0;
                        results.fulfillment_cost[position] = 0.0;
                        results.ads_spend[position] = 0.0;
                        results.other_costs[position] = 0.0;
                        results.total_costs[position] = 0.0;
                    }

                    var total_costs = profit.fulfillment_cost + profit.ad_spend + profit.other_costs;
                    results.revenue[position] = +(results.revenue[position] + profit.revenue).toFixed(2);
                    results.fulfillment_cost[position] = +(results.fulfillment_cost[position] + profit.fulfillment_cost).toFixed(2);
                    results.ads_spend[position] = +(results.ads_spend[position] + profit.ad_spend).toFixed(2);
                    results.other_costs[position] = +(results.other_costs[position] + profit.other_costs).toFixed(2);
                    results.total_costs[position] = +(results.total_costs[position] + total_costs).toFixed(2);
                }
            } else if (this.chartTime == 'monthly') {
                var lastDate = ''
                    position = -1;

                for (var iLength = this.profitsData.length, i = 0; i <= iLength; i++) {
                    var profit = this.profitsData[i];
                    if (!profit) {
                        continue;
                    }
                    var currentDate = profit.date_as_string.replace(/\/\d{2}\//, ''),
                        total_costs = profit.fulfillment_cost + profit.ad_spend + profit.other_costs;

                    if (currentDate != lastDate) {
                        position += 1;
                        lastDate = currentDate;
                        results.revenue[position] = +profit.revenue.toFixed(2);
                        results.fulfillment_cost[position] = +profit.fulfillment_cost.toFixed(2);
                        results.ads_spend[position] = +profit.ad_spend.toFixed(2);
                        results.other_costs[position] = +profit.other_costs.toFixed(2);
                        results.total_costs[position] = +total_costs.toFixed(2);
                    } else {
                        results.revenue[position] = +(results.revenue[position] + profit.revenue).toFixed(2);
                        results.fulfillment_cost[position] = +(results.fulfillment_cost[position] + profit.fulfillment_cost).toFixed(2);
                        results.ads_spend[position] = +(results.ads_spend[position] + profit.ad_spend).toFixed(2);
                        results.other_costs[position] = +(results.other_costs[position] + profit.other_costs).toFixed(2);
                        results.total_costs[position] = +(results.total_costs[position] + total_costs).toFixed(2);
                    }
                }
            }

            this.activateGraphView($('#graph-view ' + activeGraphViewCssClass));

            this.chartsData = results;
        },
        loadChartLabels: function(start, end) {
            var result = [];

            if (this.chartTime == 'daily') {
                while (start <= end) {
                    result.push(start.format('MMM DD, YYYY'));
                    start.add(1, 'days');
                }
            } else if (this.chartTime == 'weekly') {
                var day = 1,  // Monday
                    current = start.clone();

                end.add(7, 'days');
                result.push(current.format('MMM DD, YYYY'));
                while (current.add(1, 'week').isBefore(end)) {
                    result.push(current.format('MMM DD, YYYY'));
                }
            } else if (this.chartTime == 'monthly') {
                var end = end.toDate(),
                    start = start.toDate(),
                    ydiff = end.getYear() - start.getYear(),
                    mdiff = end.getMonth() - start.getMonth();
                    diff = (ydiff * 12 + mdiff);

                for (var i = 0; i <= diff; i++) {
                    if (i == 0) {
                        start.setMonth(start.getMonth());
                    } else {
                        start.setMonth(start.getMonth() + 1);
                    }

                    result[i] = moment(start).format("MMM YYYY");
                }
            }

            this.chartsLabels = result;
        },
        setChartViewByDate: function(start, end) {
            monthsBetween = moment(end - start).month();
            if (monthsBetween < this.min_months_for_daily_chart) {
                this.chartTime = 'daily';
            } else if (monthsBetween < this.min_months_for_weekly_chart) {
                this.chartTime = 'weekly';
            } else {
                this.chartTime = 'monthly';
            }
        },
        initializeChartsData: function() {
            var end = moment($('input[name="end"]').val().replace(/(\d{2}).?(\d{2}).?(\d{4})$/, '$3-$1-$2')),
                start = moment($('input[name="start"]').val().replace(/(\d{2}).?(\d{2}).?(\d{4})$/, '$3-$1-$2'));

            this.setChartViewByDate(start, end);
            this.loadChartsData();
            this.loadChartLabels(start, end);

            this.profitChartData = {
                labels: this.chartsLabels,
                datasets: [
                    {
                        label: "Revenue",
                        fill: false,
                        backgroundColor: 'rgba(125, 171, 196, 0.5)',
                        borderColor: "rgba(125, 171, 196, 0.7)",
                        dataKey: 'revenue',
                        data: this.chartsData.revenue
                    }, {
                        label: "Total Costs",
                        fill: false,
                        backgroundColor: 'rgba(236, 71, 88, 0.5)',
                        borderColor: "rgba(236, 71, 88, 0.7)",
                        dataKey: 'total_costs',
                        data: this.chartsData.total_costs
                    }
                ]
            };
        },
        loadCharts: function() {
            var ctx = $("#profits-chart").get(0).getContext("2d");
            this.profitChart = new Chart(ctx, {
                type: 'line',
                data: this.profitChartData,
                options: {
                    responsive: true,
                    tooltips: {mode: 'index', intersect: false},
                    hover: {mode: 'nearest', intersect: true},
                    scales: {
                        yAxes: [{
                            ticks: {
                                beginAtZero: true,
                                callback: function(value, index, values) {
                                    return Currency.format(value);
                                }
                            }
                        }]
                    }
                }
            });
        },
        reloadCharts: function() {
            var end = moment($('input[name="end"]').val().replace(/(\d{2}).?(\d{2}).?(\d{4})$/, '$3-$1-$2')),
                start = moment($('input[name="start"]').val().replace(/(\d{2}).?(\d{2}).?(\d{4})$/, '$3-$1-$2'));

            this.loadChartsData();
            this.loadChartLabels(start, end);

            this.profitChartData.labels = this.chartsLabels;
            this.profitChartData.datasets.forEach(function(dataset) {
                dataset.data = ProfitDashboard.chartsData[dataset.dataKey];
            });

            this.profitChart.update();
        },
        activateGraphView: function(btn) {
            $('#graph-view .btn.btn-success').removeClass('active btn-success').addClass('btn-default');
            btn.removeClass('btn-default').addClass('active btn-success');
        },
        onGraphViewClick: function() {
            $('#graph-view .btn').on('click', function(e) {
                e.preventDefault();

                ProfitDashboard.activateGraphView($(this));
                ProfitDashboard.chartTime = $(this).attr('data-time');
                ProfitDashboard.reloadCharts();
            });
        },
        onTabsChange: function() {
            $('#top-controls-menu .nav-tabs li a').on('click', function() {
                var showControls = $(this).attr('data-top-controls');
                $('.top-controls').addClass('hidden');
                $(showControls).removeClass('hidden');
                window.location.hash = $(this).attr('href').replace('#', '');
            });
        },
        onChartToggleDataClick: function() {
            $('#tab-charts .chart .toggle-data').on('click', function(e) {
                e.preventDefault();

                var label = $(this).attr('data-label'),
                    dataKey = $(this).attr('data-key'),
                    addDataset = !$(this).hasClass('active');

                if (addDataset) {
                    $(this).addClass('active');

                    ProfitDashboard.profitChartData.datasets.push(
                        {
                            label: label,
                            fill: false,
                            backgroundColor: 'rgba(248, 172, 89, 0.5)',
                            borderColor: "rgba(248, 172, 89, 0.7)",
                            dataKey: dataKey,
                            data: ProfitDashboard.chartsData[dataKey]
                        }
                    );
                } else {
                    $(this).removeClass('active');

                    ProfitDashboard.profitChartData.datasets = $.map(ProfitDashboard.profitChartData.datasets, function(dataset) {
                        if (dataset.dataKey != dataKey) {
                            return dataset;
                        }
                    });
                }

                ProfitDashboard.profitChart.update();
            });
        }
    };

    ProfitDashboard.init();
})();


// Facebook Sync
var FacebookProfitDashboard = {
    firstTime: true,
    init: function() {
        this.onFacebookSyncFormSubmit();
        this.facebookStatus.connect();
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
    onFacebookSyncFormSubmit: function() {
        $('#facebook-sync').on('submit', function(e) {
            e.preventDefault();

            FacebookProfitDashboard.facebookStatus.loading();
            $.ajax({
                type: $(this).attr('method'),
                url: $(this).attr('action'),
                data: $(this).serialize(),
                dataType: 'json',
                success: function(result) {
                    if (result.success) {
                        FacebookProfitDashboard.facebookInsightsPusherNotification();
                    }
                },
                error: function (data) {
                    displayAjaxError('Facebook Ad Sync', data);
                }
            });
        });
    },
    statusChangeCallback: function(response) {
        // The response object is returned with a status field that lets the
        // app know the current login status of the person.
        // Full docs on the response object can be found in the documentation
        // for FB.getLoginStatus().
        if (response.status === 'connected' && !FacebookProfitDashboard.firstTime) {
            FacebookProfitDashboard.facebookStatus.loggedIn();

            $('input[name="fb_access_token"]').val(response.authResponse.accessToken);
            $('#fb-ad-setup').trigger('click');
        } else {
            if (response.authResponse) {
                FacebookProfitDashboard.facebookStatus.loggedIn();
                $('input[name="fb_access_token"]').val(response.authResponse.accessToken);
            } else {
                FacebookProfitDashboard.facebookStatus.connect();
            }
        }
        FacebookProfitDashboard.firstTime = false;
        $('#facebook-insights').css('display', '');
    },
    checkLoginState: function() {
        FB.getLoginStatus(function(response) {
            FacebookProfitDashboard.statusChangeCallback(response);
        });
    },
    facebookInsightsPusherNotification: function() {
        var pusher = new Pusher(config.sub_conf.key);
        var channel = pusher.subscribe(config.sub_conf.channel);

        channel.bind('facebook-insights', function(data) {
            if (data.success) {
                setTimeout(function() {
                    FacebookProfitDashboard.facebookStatus.loggedIn();
                    window.location.reload();
                }, 1000);
            } else {
                displayAjaxError('Facebook Insights', data);
                FacebookProfitDashboard.facebookStatus.loggedIn();
                $('#last-synced').text('Error');
            }
        });
    }
};

FacebookProfitDashboard.init();

window.fbAsyncInit = function() {
    if (!config.facebook.appId) {
        return;
    }

    FB.init({
        appId      : config.facebook.appId,
        cookie     : true,  // enable cookies to allow the server to access the session
        xfbml      : true,  // parse social plugins on this page
        version    : 'v2.8' // use graph api version 2.8
    });

    FB.getLoginStatus(function(response) {
        FacebookProfitDashboard.statusChangeCallback(response);
    });

    FB.Event.subscribe('auth.logout', FacebookProfitDashboard.facebookStatus.connect);
};

$(function () {
    $('#fb-ad-setup').click(function(e) {
        e.preventDefault();

        $.ajax({
            url: '/profit-dashboard/facebook/accounts',
            data: {
                fb_access_token: $('input[name="fb_access_token"]').val()
            },
        }).done(function(data) {
            var template = Handlebars.compile($("#fb-account-list").html());

            $('#fb-account-select-modal .modal-body').html(template(data));
            $('#fb-account-select-modal').modal('show');
        }).fail(function(data) {
            displayAjaxError('Ad Account Selection', data);
        });
    });

    $('#fb-account-selected').click(function (e) {
        e.preventDefault();

        var account_id = $('#fb-account-select-modal [name="account"]').val();

        $.ajax({
            url: '/profit-dashboard/facebook/campaign',
            data: {
                fb_access_token: $('input[name="fb_access_token"]').val(),
                account_id: account_id,
            },
        }).done(function(data) {
            $('#fb-account-select-modal').modal('hide');

            var template = Handlebars.compile($("#fb-campaign-list").html());

            $('#fb-campaign-select-modal .modal-body').html(template(data));
            $('#fb-campaign-select-modal').modal('show');

            $('.select-all-btn').click(function (e) {
                e.preventDefault();

                var status = $(this).prop('status');
                status = typeof(status) === 'undefined' ? true : status;

                $(this).parents('.modal-body').find('input[type=checkbox]').prop('checked', status);


                $(this).text(status ? 'Select None' : 'Select All');
                $(this).prop('status', !status);
            });
        }).fail(function(data) {
            displayAjaxError('Campaign Selection', data);
        });
    });

    $('#fb-campaign-selected').click(function (e) {
        e.preventDefault();

        var campaigns = $.map($('[name="campaign"]:checked'), function(el) {
            return el.value;
        });

        $('#fb-campaign-select-modal').modal('hide');

        FacebookProfitDashboard.facebookStatus.loading();
        $.ajax({
            type: 'post',
            url: '/profit-dashboard/facebook/insights',
            data: {
                'fb_access_token': $('input[name="fb_access_token"]').val(),
                'accounts': $('#fb-account-select-modal [name="account"]').val(),
                'campaigns': campaigns.join(','),
                'config': $('#fb-account-select-modal [name="config"]').val()
            },
            dataType: 'json',
            success: function(result) {
                if (result.success) {
                    FacebookProfitDashboard.facebookInsightsPusherNotification();
                }
            },
            error: function (data) {
                displayAjaxError('Facebook Ad Sync', data);
            }
        });
    });
});
