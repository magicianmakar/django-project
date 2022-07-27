(function() {
    'use strict';

    function processCustomInfo(wrapper, order) {
        var fromCountry = wrapper.find('[name="warehouse"] option:selected').data('country-code');
        var toCountry = wrapper.find('[name="to_address_country_code"]').val();

        if (fromCountry && toCountry && fromCountry !== toCountry) {
            wrapper.find('.customs-item').each(function() {
                if (wrapper.find('[name="order_data_id"][value="' + $(this).attr('data-id') + '"]').length === 0) {
                    $(this).remove();
                }
            });
            wrapper.find('[name="order_data_id"]').each(function() {
                var orderDataId = $(this).val();
                if (wrapper.find('.customs-item[data-id="' + orderDataId + '"]').length) {
                    return true;
                }

                var item = $(this).data('json');
                if (order) {
                    for (var i = 0, iLength = order.items.length; i < iLength; i++) {
                        if (order.items[i].order_data_id === orderDataId) {
                            item = $.extend({}, order.items[i]);
                        }
                    }
                }

                var customsItem = Handlebars.compile($("#customs-item").html());
                item['countries'] = logisticsCountries;
                customsItem = customsItem(item);

                wrapper.find('.customs-items').append(customsItem);
                wrapper.find('.customs-item[data-id="' + orderDataId + '"] [name="item_country_code"]').val('US');
            });
        } else {
            wrapper.find('.customs-items').empty();
        }
    }

    function getLogisticsData(e, extraParams) {
        if (e && e.preventDefault) {
            e.preventDefault();
        }

        if (!extraParams) {
            extraParams = {};
        }
        extraParams = $.extend({}, {warehouses: {}, packages: {}, rates: {}, address: {}, refresh: {}, customs_items: {}}, extraParams);

        var orderDataIds = [];
        $('.logistics-order').each(function() {
            var orderId = $(this).find('[name="order_id"]').val();
            extraParams.rates[orderId] = $(this).find('.logistics-carrier.active input[name="rate_id"]').val();
            extraParams.packages[orderId] = {
                weight: $(this).find('[name="weight"]').val(),
                length: $(this).find('[name="length"]').val(),
                width: $(this).find('[name="width"]').val(),
                height: $(this).find('[name="height"]').val(),
            };

            $(this).find('.logistics-shipment').each(function() {
                var warehouse_id = $(this).find('[name="warehouse"]').val();
                $(this).find('[name="order_data_id"]').each(function() {
                    var orderDataId = $(this).val();
                    extraParams.warehouses[orderDataId] = warehouse_id;
                    orderDataIds.push(orderDataId);
                });
            });

            $(this).find('[name^="to_address_"]').each(function() {
                var key = $(this).attr('name').replace('to_address_', '');
                extraParams['address'][key] = $(this).val() || '';
            });

            extraParams['refresh'][orderId] = $(this).find('[name="refresh"]').val();

            $(this).find('.customs-item').each(function() {
                extraParams['customs_items'][$(this).attr('data-id')] = {
                    'weight': $(this).find('[name="item_weight"]').val(),
                    'hs_tariff': $(this).find('[name="item_hs_tariff"]').val(),
                    'country_code': $(this).find('[name="item_country_code"]').val(),
                };
            });
        });

        if (orderDataIds.length) {
            processOrders(orderDataIds, extraParams);
        } else {
            toastr.warning("No orders left for processing.");
        }
    }

    function processOrders(orderDataIds, extraParams) {
        var postData = $.extend({
            'order_data_ids': orderDataIds,
            'store_type': window.storeType,
            'store_id': STORE_ID,
        }, extraParams);

        $.ajax({
            url: api_url('shipping', 'logistics'),
            type: "POST",
            data: JSON.stringify(postData),
            dataType: 'json',
            contentType: 'application/json',
            beforeSend: function() {
                if ($('#modal-logistics-order-detail:visible').length === 0) {
                    $('#modal-logistics-order-detail').modal('show');
                }
                $('#modal-logistics-order-detail .modal-content').addClass('loading');
                $('#modal-logistics-order-detail .logistics-label').addClass('hidden');
                $('#modal-logistics-order-detail .modal-footer').addClass('hidden');

                $('#logistics-label-actions').addClass('hidden');
                $('#logistics-shipment-actions').removeClass('hidden');

                $('.refresh-carriers').addClass('hidden');
                $('.logistics-carriers').css('top', '0');
            },
            success: function (data) {
                if (data.error) {
                    displayAjaxError('3PL', data.error, true);
                }
                var order = data.orders[0];
                var wrapper = $('#modal-logistics-order-detail .logistics-order');

                var shipmentWrapper = wrapper.find('.logistics-shipment');
                shipmentWrapper.find('[name="warehouse"]').val(order.warehouse_id);
                shipmentWrapper.find('[name="order_data_id"]').remove();
                for (var i = 0, iLength = data.orders.length; i < iLength; i++) {  // TODO: remove when implementing bulk ordering
                    for (var j = 0, jLength = data.orders[i].items.length; j < jLength; j++) {
                        var item = data.orders[i].items[j];
                        shipmentWrapper.append($('<input type="hidden" name="order_data_id">').val(item.order_data_id).data('json', item));
                    }
                }
                wrapper.find('.logistics-errors').empty();
                if (order.shipment && order.shipment.errors) {
                    for (i = 0, iLength = order.shipment.errors.length; i < iLength; i++) {
                        wrapper.find('.logistics-errors').append($('<div class="alert alert-danger">').text(order.shipment.errors[i]));
                    }
                }

                if (order.to_address.errors) {
                    for (i = 0, iLength = order.to_address.errors.length; i < iLength; i++) {
                        wrapper.find('.logistics-errors').append($('<div class="alert alert-danger">').text(order.to_address.errors[i]));
                    }
                }
                wrapper.find('[name="order_id"]').val(order.id);
                wrapper.find('[name="length"]').val(order.length);
                wrapper.find('[name="width"]').val(order.width);
                wrapper.find('[name="height"]').val(order.height);
                if (order.weight) {
                    wrapper.find('[name="weight"]').val(order.weight);
                } else {
                    wrapper.find('[name="weight"]').val(order.weight);
                }

                wrapper.find('[name^="to_address_"]').each(function() {
                    var key = $(this).attr('name').replace('to_address_', '');
                    $(this).val(order.to_address[key]);
                });

                processCustomInfo(wrapper);

                if (!order.rate_id) {
                    wrapper.find('.create-logistics-label').removeClass('hidden');
                    wrapper.find('.buy-logistics-label').addClass('hidden');
                }

                wrapper.find('[name="refresh"]').val('');

                // Cleanup
                var carriersElem = wrapper.find('.logistics-carriers');
                wrapper.find('.logistics-label-image').empty();
                if (postData.refresh && postData.refresh[order.id] === "1") {
                    carriersElem.empty();
                } else {
                    carriersElem.children(':not(.logistics-carrier)').remove();
                }
                wrapper.find('.buy-logistics-label').prop('disabled', false);
                if (!order.shipment.rates) {
                    return true;
                }

                $('#logistics-result').css('display', '');
                $('#logistics-info').addClass('col-md-7').removeClass('col-md-12');
                $('#modal-logistics-order-detail .modal-dialog').addClass('modal-lg');

                if (order.shipment.rates.length > 0 && !order.shipment.selected_rate) {
                    wrapper.find('.refresh-carriers').removeClass('hidden');
                    carriersElem.css('top', '40px');
                }
                if (carriersElem.find('.logistics-carrier').length === 0) {
                    var shipmentRate = Handlebars.compile($("#shipment-rate").html());
                    for (i = 0, iLength = order.shipment.rates.length; i < iLength; i++) {
                        var rate = order.shipment.rates[i];
                        var currencySign = '$';
                        if (rate.currency !== 'USD') {
                            currencySign = ' ' + rate.currency;
                        }

                        rate['currencySign'] = currencySign;
                        rate['est_delivery_days'] = rate.est_delivery_days ? 'Estimate delivery in ' + rate.est_delivery_days + ' day(s).' : '';
                        var logisticsCarrier = $(shipmentRate(rate));
                        carriersElem.append(logisticsCarrier);
                        if (order.rate_id == rate.id) {
                            logisticsCarrier.trigger('click');
                        }
                    }
                }

                if (order.label_url) {
                    var labelName = order.label_url.split('/');
                    labelName = labelName[labelName.length - 1];
                    wrapper.find('.logistics-label-image').append(
                        $('<a target="_blank">').attr({'href': order.label_url, 'download': labelName}).append(
                          $('<img class="img-responsive">').attr('src', order.label_url)
                        )
                    );
                    $('#logistics-label-actions').removeClass('hidden').attr({'href': order.label_url, 'download': labelName});
                    $('#logistics-shipment-actions').addClass('hidden');
                    $('#logistics-print-label').attr('image-url', order.label_url);
                    $('#logistics-download-label').attr('href', order.label_url);
                }

                if (order.shipment.selected_rate) {
                    wrapper.find('.buy-logistics-label').prop('disabled', true);
                }
            },
            error: function(data) {
                displayAjaxError('3PL', data, true);
            },
            complete: function() {
                $('#modal-logistics-order-detail .modal-content').removeClass('loading');
                $('#modal-logistics-order-detail .logistics-label').removeClass('hidden');
                $('#modal-logistics-order-detail .modal-footer').removeClass('hidden');
            }
        });
    }

    $(".create-logistics-order").on('click', function (e) {
        e.preventDefault();
        var orderDataIds = [];
        var extraParams = {warehouses: {}};
        var checkedItems = $(this).parents('.order').find('.line-checkbox:checkbox:checked');
        if (checkedItems.length === 0) {
            checkedItems = $(this).parents('.order').find('.line-checkbox:checkbox');
            checkedItems.iCheck('check');
        }

        var notConnected = false;
        var isOrdered = false;
        checkedItems.each(function (i, item) {
            var line = $(item).parents('.line');
            if (line.attr('raw-order-data-id')) {
                notConnected = true;
            }
            if (line.attr('line-track')) {
                isOrdered = true;
            }
            orderDataIds.push(line.attr('order-data-id') || line.attr('raw-order-data-id'));
        });

        if (!orderDataIds.length) {
            toastr.warning("Please select orders for processing.");
            return;
        }

        if (notConnected && !isOrdered) {
            swal({
                title: 'Unconnected Product(s)',
                text: "One or more products aren't connected to Dropified, would you like to connect before creating a label?",
                type: "warning",
                showCancelButton: true,
                animation: false,
                cancelButtonText: "No",
                confirmButtonText: 'Yes',
                confirmButtonColor: "#DD6B55",
                closeOnCancel: true,
                closeOnConfirm: true,
                showLoaderOnConfirm: true,
            },
            function(isConfirm) {
                extraParams['connect_products'] = isConfirm;
                processOrders(orderDataIds, extraParams);
            });
        } else {
            processOrders(orderDataIds, extraParams);
        }
    });

    $('.create-logistics-label, .buy-logistics-label').on('click', getLogisticsData);

    $('.logistics-order').on('click', '.logistics-carrier', function(e) {
        var wrapper = $(this).parents('.logistics-order');
        if ($(this).hasClass('active')) {
            $(this).removeClass('active');
            wrapper.find('.create-logistics-label').removeClass('hidden');
            wrapper.find('.buy-logistics-label').addClass('hidden');
        } else {
            $(this).siblings('.logistics-carrier').removeClass('active');
            $(this).addClass('active');
            wrapper.find('.create-logistics-label').addClass('hidden');
            wrapper.find('.buy-logistics-label').removeClass('hidden');
        }
    }).on('click', '.refresh-carriers', function(e) {
        $(this).parents('.logistics-order').find('[name="refresh"]').val('1');
        getLogisticsData(e);
    });

    $('#modal-logistics-order-detail').on('show.bs.modal', function() {
        $(this).find('.form').trigger('reset');
        $('#logistics-result').css('display', 'none');
        $('#logistics-info').addClass('col-md-12').removeClass('col-md-7');
        $('#modal-logistics-order-detail .modal-dialog').removeClass('modal-lg');
    });

    $('#modal-logistics-order-detail .form').on('change', function() {
        $(this).find('[name="refresh"]').val('1');
    });

    $('[name="warehouse"]').on('change', function() {
        var order = $(this).parents('.logistics-order');
        processCustomInfo(order);
    });

    $('#logistics-print-label').on('click', function(e) {
        e.preventDefault();
        var imageUrl = $('#logistics-print-label').attr('image-url');
        if (imageUrl) {
            $('body').addClass('with-label-url').after(
                $('<img src="' + imageUrl + '" id="logistics-label-image">').on('load', function() {
                    window.print();
                    $('body').removeClass('with-label-url');
                    $('#logistics-label-image').remove();
                })
            );
        }
    });
})();
