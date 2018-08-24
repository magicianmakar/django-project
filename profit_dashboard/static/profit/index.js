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

Handlebars.registerHelper("currencyFormat", function(amount, noSign) {
    if (!amount) return '';
    return Currency.format(amount, noSign);
});

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
            this.onTableViewClick();
            this.onTabsChange();
            this.onChartToggleDataClick();
            this.onDetailsPaginationClick();
            this.onDetailsClick();

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
            var previousIndex = null,
                previousRow = null,
                startingRow = null,
                countEmptySequence = 0;

            $('#profits tbody .tooltip').remove();
            $('#profits tbody tr.empty').each(function() {
                var currentIndex = $(this).index();
                if (previousIndex == currentIndex - 1) {
                    // Empty rows in sequence
                    $(this).css('display', 'none');
                    countEmptySequence += 1;
                } else {
                    if (startingRow != null && countEmptySequence > 0) {
                        ProfitDashboard.fillDateRange(startingRow, previousRow);
                        startingRow.find('.actions').append($('<a href="#" class="open-dates"><i class="glyphicon glyphicon-chevron-down">'));
                        startingRow.tooltip('destroy');
                    }

                    countEmptySequence = 0;
                    startingRow = $(this);
                }

                previousIndex = currentIndex;
                previousRow = $(this);
            });

            if (startingRow != null && previousRow != null && countEmptySequence > 0) {
                ProfitDashboard.fillDateRange(startingRow, previousRow);
                startingRow.find('.actions').append($('<a href="#" class="open-dates"><i class="glyphicon glyphicon-chevron-down">'));
                startingRow.tooltip('destroy');
            }
        },
        fillDateRange: function(startingRow, previousRow) {
            var startDate = startingRow.find('td:first');
            startingRow.attr('data-initial-text', startDate.text()).addClass('closed');
            startDate.text(startDate.text() + ' - ' + previousRow.find('td:first').text());
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

                // Replace date for first row and start tooltip again
                selectedRow.find('td:first').text(selectedRow.attr('data-initial-text'));
                selectedRow.tooltip();

                // Show next rows
                selectedRow.nextUntil('.closed, .opened', '.empty').css('display', '');

                // Change row actions to a opened kind
                $(this).find('.glyphicon').removeClass('glyphicon-chevron-down').addClass('glyphicon-chevron-up');
                $(this).removeClass('open-dates').addClass('close-dates');
                selectedRow.addClass('opened').removeClass('closed');

                ProfitDashboard.fixStripes();
            });
        },
        onClickCloseDates: function() {
            $('#profits').on('click', 'tr .actions a.close-dates', function(e) {
                e.preventDefault();

                var selectedRow = $(this).parents('.profit');

                // Remove weekday tooltip
                selectedRow.tooltip('destroy');

                // Replace date for first row and hide next rows
                var lastRow = selectedRow.nextUntil('.closed, .opened', '.empty').css('display', 'none').filter(':last');
                var dateColumn = $(this).parents('.profit').find('td:first');
                dateColumn.text(dateColumn.text() + ' - ' + lastRow.find('td:first').text());

                // Change row actions to a closed kind
                selectedRow.addClass('closed').removeClass('opened');
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
                    profitAmount = otherCosts.parent().find('.profit-amount span'),
                    totalCostsValue = parseFloat(totalCosts.attr('data-original-amount')),
                    profitAmountValue = parseFloat(profitAmount.attr('data-original-amount')),
                    revenue = parseFloat(otherCosts.parent().find('.revenue').attr('data-original-amount')),
                    percentage = otherCosts.parent().find('.percentage');

                if (isNaN(inputValue)) {
                    inputValue = 0;
                }

                value = inputValue - originalValue;
                totalCosts.text((totalCostsValue + value).toFixed(2));
                profitAmount.text((profitAmountValue - value).toFixed(2));
                var percentageAmount = parseInt((profitAmountValue - value) / revenue * 100);
                if (isNaN(percentageAmount)) {
                    percentageAmount = 0;
                }
                percentage.text(percentageAmount + '%');

                var updatedTotalCosts = totalCostsValue + value,
                    updatedProfitValue = profitAmountValue - value;

                otherCosts.attr('data-original-amount', inputValue.toFixed(2));
                totalCosts.attr('data-original-amount', updatedTotalCosts.toFixed(2));
                profitAmount.attr('data-original-amount', updatedProfitValue.toFixed(2));

                ProfitDashboard.totalsProfitAmount -= value;
                ProfitDashboard.totalsOtherCostsAmount += value;
                ProfitDashboard.totalsTotalCostsAmount += value;
                $('#totals-profit').text(Currency.format(ProfitDashboard.totalsProfitAmount, true));
                $('#totals-other-costs').text(Currency.format(ProfitDashboard.totalsOtherCostsAmount, true));
                $('#totals-total-costs').text(Currency.format(ProfitDashboard.totalsTotalCostsAmount, true));

                $(this).off('blur');

                var profitWasEmpty = $(this).parents('.profit').hasClass('empty'),
                    profitIsEmpty = updatedTotalCosts == 0 && updatedProfitValue == 0;

                if (profitIsEmpty) {
                    $(this).parents('.profit').addClass('empty');
                } else {
                    $(this).parents('.profit').removeClass('empty');
                }

                if (profitIsEmpty != profitWasEmpty) {
                    ProfitDashboard.attachReloadExpandanble($(this));
                }

                ProfitDashboard.saveOtherCost($(this), inputValue, value);
            });
        },
        attachReloadExpandanble: function(totalCostsInput) {
            totalCostsInput.one('blur', function() {
                ProfitDashboard.reloadExpandable();
                ProfitDashboard.fixStripes();
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
                        if (data.status != 'ok') {
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
            var results = {revenue: [], fulfillment_cost: [], ads_spend: [], other_costs: [], total_costs: [], fulfillments_count: []},
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
                    results.fulfillments_count.push(+profit.fulfillments_count);
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
                results.fulfillments_count[position] = 0;
                results.total_costs[position] = 0.0;
                for (var iLength = this.profitsData.length, i = 0; i <= iLength; i++) {
                    var profit = this.profitsData[i];
                    if (!profit) {
                        continue;
                    }

                    var profitDate = moment(profit.date_as_string.replace(/(\d{2}).?(\d{2}).?(\d{4})$/, '$3-$1-$2'));
                    if (profitDate.isAfter(nextMonday)) {
                        position += 1;
                        nextMonday = nextMonday.add(1, 'weeks');

                        results.revenue[position] = 0.0;
                        results.fulfillment_cost[position] = 0.0;
                        results.ads_spend[position] = 0.0;
                        results.other_costs[position] = 0.0;
                        results.fulfillments_count[position] = 0;
                        results.total_costs[position] = 0.0;
                    }

                    var total_costs = profit.fulfillment_cost + profit.ad_spend + profit.other_costs;
                    results.revenue[position] = +(results.revenue[position] + profit.revenue).toFixed(2);
                    results.fulfillment_cost[position] = +(results.fulfillment_cost[position] + profit.fulfillment_cost).toFixed(2);
                    results.ads_spend[position] = +(results.ads_spend[position] + profit.ad_spend).toFixed(2);
                    results.other_costs[position] = +(results.other_costs[position] + profit.other_costs).toFixed(2);
                    results.fulfillments_count[position] = +(results.fulfillments_count[position] + profit.fulfillments_count).toFixed(2);
                    results.total_costs[position] = +(results.total_costs[position] + total_costs).toFixed(2);
                }
            } else if (this.chartTime == 'monthly') {
                var lastDate = '',
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
                        results.fulfillments_count[position] = +profit.fulfillments_count;
                        results.total_costs[position] = +total_costs.toFixed(2);

                    } else {
                        results.revenue[position] = +(results.revenue[position] + profit.revenue).toFixed(2);
                        results.fulfillment_cost[position] = +(results.fulfillment_cost[position] + profit.fulfillment_cost).toFixed(2);
                        results.ads_spend[position] = +(results.ads_spend[position] + profit.ad_spend).toFixed(2);
                        results.other_costs[position] = +(results.other_costs[position] + profit.other_costs).toFixed(2);
                        results.fulfillments_count[position] = +(results.fulfillments_count[position] + profit.fulfillments_count);
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
                            id: 'currency',
                            ticks: {
                                beginAtZero: true,
                                callback: function(value, index, values) {
                                    return Currency.format(value);
                                }
                            }
                        }, {
                            id: 'number',
                            position: 'right',
                            display: false,
                            gridLines: {
                                display: false
                            },
                            ticks: {
                                min: 0,
                                fontColor: "rgba(147, 198, 126, 0.5)",
                                backgroundColor: "rgba(147, 198, 126, 0.7)"
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
        activateTableView: function(btn) {
            $('#table-view .btn.btn-success').removeClass('active btn-success').addClass('btn-default');
            btn.removeClass('btn-default').addClass('active btn-success');
        },
        onTableViewClick: function() {
            $('#table-view').on('click', '.btn:not(.active)', function(e) {
                e.preventDefault();

                var timeType = $(this).attr('data-time');
                ProfitDashboard.activateTableView($(this));

                if (timeType == 'weekly') {
                    $('#profits').addClass('weekly').removeClass('daily');
                    ProfitDashboard.profitsWeekly();
                }
                if (timeType == 'daily') {
                    $('#profits').addClass('daily').removeClass('weekly');
                    ProfitDashboard.profitsDaily();
                }
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
                    dataYAxes = $(this).attr('data-y-axes'),
                    addDataset = !$(this).hasClass('active');

                if (addDataset) {
                    $(this).addClass('active');

                    var dataset = {
                        label: label,
                        fill: false,
                        backgroundColor: 'rgba(248, 172, 89, 0.5)',
                        borderColor: "rgba(248, 172, 89, 0.7)",
                        dataKey: dataKey,
                        data: ProfitDashboard.chartsData[dataKey]
                    };

                    if (dataYAxes == 'number') {
                        dataset['yAxisID'] = 'number';
                        ProfitDashboard.profitChart.options.scales.yAxes[1].display = true;
                        ProfitDashboard.profitChart.options.scales.yAxes[1].ticks.suggestedMax = Math.max.apply(null, dataset.data) + 1;
                        dataset.borderColor = ProfitDashboard.profitChart.options.scales.yAxes[1].ticks.fontColor;
                        dataset.backgroundColor = ProfitDashboard.profitChart.options.scales.yAxes[1].ticks.backgroundColor;
                    }

                    ProfitDashboard.profitChartData.datasets.push(dataset);
                } else {
                    $(this).removeClass('active');

                    if (dataYAxes == 'number' && $('#tab-charts .toggle-data.active[data-y-axes="number"]').length == 0) {
                        ProfitDashboard.profitChart.options.scales.yAxes[1].display = false;
                    }

                    ProfitDashboard.profitChartData.datasets = $.map(ProfitDashboard.profitChartData.datasets, function(dataset) {
                        if (dataset.dataKey != dataKey) {
                            return dataset;
                        }
                    });
                }

                ProfitDashboard.profitChart.update();
            });
        },
        outputToRow: function(profitRow, profitAmounts) {
            profitRow.find('td:nth-child(1)').text(profitAmounts.date_as_string);
            profitRow.find('td:nth-child(2)').text(Currency.format(profitAmounts.revenue));
            profitRow.find('td:nth-child(3)').text(Currency.format(profitAmounts.fulfillment_cost));
            profitRow.find('td:nth-child(4)').text(Currency.format(profitAmounts.ad_spend));
            profitRow.find('td:nth-child(5) .other-costs-value').text(Currency.format(profitAmounts.other_costs));

            var outcome = profitAmounts.fulfillment_cost + profitAmounts.ad_spend + profitAmounts.other_costs,
                profit = profitAmounts.revenue - outcome,
                percentage = profit / profitAmounts.revenue * 100;

            if (percentage < 0) {
                percentage = 0;
            }
            if (percentage > 100 || isNaN(percentage)) {
                percentage = 100;
            }

            profitRow.find('td:nth-child(6) span').text(Currency.format(outcome, true));
            profitRow.find('td:nth-child(7) span').text(Currency.format(profit, true));
            profitRow.find('td:nth-child(8)').text(parseInt(percentage) + '%');
        },
        refreshWeeklyData: function(profitData) {
            return {
                revenue: profitData.revenue,
                other_costs: profitData.other_costs,
                date_as_string: profitData.date_as_string,
                ad_spend: profitData.ad_spend,
                fulfillment_cost: profitData.fulfillment_cost
            };
        },
        sumWeeklyData: function(weeklyData, profitData) {
            return {
                revenue: weeklyData.revenue + profitData.revenue,
                other_costs: weeklyData.other_costs + profitData.other_costs,
                date_as_string: weeklyData.date_as_string,
                ad_spend: weeklyData.ad_spend + profitData.ad_spend,
                fulfillment_cost: weeklyData.fulfillment_cost + profitData.fulfillment_cost
            };
        },
        profitsWeekly: function() {
            var countDays = -1,
                lastProfit = null,
                firstWeekDayRow = null,
                weeklyAmounts = ProfitDashboard.refreshWeeklyData(profitsData[0]);

            $('#profits .profit.closed').removeClass('closed');
            $('.open-dates, .close-dates', '#profits .profit .actions').remove();
            for (var i = 0, iLength = profitsData.length; i < iLength; i++) {
                var profitData = profitsData[i],
                    profitRow = $('#date-' + profitData.date_as_string.replace(/\//g, '')),
                    isFirstDay = countDays % 7 == 0;

                profitData.other_costs = parseFloat(profitRow.find('.other-costs').attr('data-original-amount'));

                if (isFirstDay || i == 0) {
                    if (firstWeekDayRow != null) {
                        if (lastProfit != null) {
                            weeklyAmounts.date_as_string += ' - ' + lastProfit.date_as_string;
                        }
                        ProfitDashboard.outputToRow(firstWeekDayRow, weeklyAmounts);
                        firstWeekDayRow.tooltip('destroy');
                    }
                    weeklyAmounts = ProfitDashboard.refreshWeeklyData(profitData);
                    firstWeekDayRow = profitRow;
                    firstWeekDayRow.addClass('closed');
                } else {
                    weeklyAmounts = ProfitDashboard.sumWeeklyData(weeklyAmounts, profitData);
                    profitRow.css('display', 'none');
                    lastProfit = $.extend({}, profitData);
                }

                countDays += 1;
            }

            var nextWeekDay = moment(lastProfit.date_as_string.replace(/(\d{2}).?(\d{2}).?(\d{4})$/, '$3-$1-$2')).add(1, 'weeks');
            weeklyAmounts.date_as_string += ' - ' + nextWeekDay.format('MM/DD/YYYY');
            ProfitDashboard.outputToRow(firstWeekDayRow, weeklyAmounts);
            firstWeekDayRow.tooltip('destroy');

            $('#profits .profit.closed').css('display', '');
            ProfitDashboard.fixStripes();
        },
        profitsDaily: function() {
            $('#profits .closed').removeClass('closed');
            for (var i = 0, iLength = profitsData.length; i < iLength; i++) {
                var profitData = profitsData[i],
                    profitRow = $('#date-' + profitData.date_as_string.replace(/\//g, ''));

                if (!profitRow.is(':visible')) {
                    profitRow.find('td:first').text(profitData.date_as_string);
                    profitRow.css('display', '');
                } else {
                    profitRow.tooltip();
                    profitRow.removeClass('closed');
                    ProfitDashboard.outputToRow(profitRow, profitData);
                }
            }
            ProfitDashboard.initExpandable();
            ProfitDashboard.fixStripes();
        },
        onDetailsPaginationClick: function() {
            $('#details-pagination').on('click', 'ul.pagination li a', function(e) {
                e.preventDefault();

                var page = $(this).attr('href').match(/page=(\d+)/)[1];
                ProfitDashboard.reloadProfitDetails(page);
            });

            $('#details-pagination').on('click', '.paginator-goto', function() {
                setTimeout(function() {
                    $('#details-pagination .paginator-goto input').unbind('keypress');
                }, 100);
            });

            $('#details-pagination').on('keypress', '.paginator-goto input', function(e) {
                if (e.which == 13) {
                    e.preventDefault();
                    var page = parseInt($(this).val().trim());
                    if (page) {
                        ProfitDashboard.reloadProfitDetails(page);
                    }

                    return false;
                }
            });
        },
        reloadProfitDetails: function(page, singleDate) {
            var data = {'page': page};

            if (singleDate) {
                var start = moment(singleDate.replace(/(\d{2}).?(\d{2}).?(\d{4})$/, '$3-$1-$2'));
                data['start'] = start.format('MM/DD/YYYY');
                data['end'] = start.add(1, 'days').format('MM/DD/YYYY');
            }

            $.ajax({
                type: 'POST',
                url: '/profit-dashboard/details',
                data: data,
                beforeSend: function() {
                    ProfitDashboard.detailsLoading.start();
                },
                success: function(data) {
                    var template = Handlebars.compile($("#profit-details").html());

                    $('#details tbody').html(template({'details': data.details}));
                    $('#details-pagination').html(data.pagination);
                },
                error: function(data) {
                    displayAjaxError('Profit Details Page', data);
                },
                complete: function() {
                    ProfitDashboard.detailsLoading.stop();
                }
            });
        },
        onDetailsClick: function() {
            $('.details-link').on('click', function(e) {
                e.preventDefault();

                ProfitDashboard.reloadProfitDetails(1, $(this).attr('data-date'));
                $('.nav li a[href="#tab-details"]').trigger('click');
            });
        },
        detailsLoading: {
            start: function() {
                $('#details-loading').css('display', '');
            },
            stop: function() {
                $('#details-loading').css('display', 'none');
            }
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
        this.onClickRemoveAccount();
    },
    onClickRemoveAccount: function() {
        $('.fb-ad-remove').on('click', function(e) {
            e.preventDefault();
            var btn = $(this);

            swal({
                    title: "Delete Synced Account Data",
                    text: "This will remove the data for this account. Are you sure you want to remove it?",
                    type: "warning",
                    showCancelButton: true,
                    closeOnConfirm: false,
                    showLoaderOnConfirm: true,
                    confirmButtonColor: "#DD6B55",
                    confirmButtonText: "Remove",
                    cancelButtonText: "Cancel"
                },
                function(isConfirmed) {
                    if (isConfirmed) {
                        $.ajax({
                            type: 'POST',
                            url: '/profit-dashboard/facebook/accounts/remove',
                            data: {id: btn.attr('data-id')},
                            success: function(data) {
                                btn.parents('.facebook-account').remove();

                                swal.close();
                                toastr.success("The account data has been deleted.", "Deleted!");
                                setTimeout(function() {
                                    window.location.reload();
                                }, 2000);
                            },
                            error: function(data) {
                                displayAjaxError('Delete Facebook Account Data', data);
                            }
                        });
                    }
                }
            );
        });
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

            // FacebookProfitDashboard.facebookStatus.loading();
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
            $('input[name="fb_expires_in"]').val(response.authResponse.expiresIn);
            $('#fb-ad-setup').trigger('click');
        } else {
            if (response.authResponse) {
                FacebookProfitDashboard.facebookStatus.loggedIn();
                $('input[name="fb_access_token"]').val(response.authResponse.accessToken);
                $('input[name="fb_expires_in"]').val(response.authResponse.expiresIn);
            } else {
                FacebookProfitDashboard.facebookStatus.connect();
            }
        }
        FacebookProfitDashboard.firstTime = false;
        // $('#facebook-insights').css('display', '');
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
                fb_access_token: $('input[name="fb_access_token"]').val(),
                fb_expires_in: $('input[name="fb_expires_in"]').val()
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

        var selectedAccount = $('#fb-account-select-modal [name="account"]:checked'),
            accountId = selectedAccount.val(),
            accountName = selectedAccount.parent('li').attr('data-name');

        $.ajax({
            url: '/profit-dashboard/facebook/campaign',
            data: {
                account_id: accountId,
                account_name: accountName
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
                'account_id': $('#fb-account-select-modal [name="account"]:checked').val(),
                'campaigns': campaigns.join(','),
                'config': $('#fb-campaign-select-modal [name="config"]').val()
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
