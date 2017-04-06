window.OrderImportsIndex = {
    data: {},
    fileIndex: 0,
	init: function() {
        this.setDropzoneOptions();
        this.onApproveSubmit();
        this.onChangeOnlyOneFilled();
        this.onKeyUpOnlyNumber();
    },
    setDropzoneOptions: function() {
        Dropzone.options.dropzoneForm = {
            paramName: "file", // The name that will be used to transfer the file
            maxFilesize: 2, // MB
            uploadMultiple: false,
            dictDefaultMessage: "<strong>Step 2: Drop files here or click to upload</strong></br>" +
                                "(After the file is dropped or selected, it will be sent to the server.)",
            acceptedFiles: '.csv',
            init: function() {
                this.on("processing", function(file) {
                    this.options.url = $('select[name="stores"]').val() + '?file_index=' + window.OrderImportsIndex.fileIndex + '&' + $('#mapping-form').serialize();
                    window.OrderImportsIndex.fileIndex += 1;
                });

                this.on("success", window.OrderImportsIndex.onDropzoneSuccess);
            }
        };
    },
    onDropzoneSuccess: function(file, result) {
        if (result.success) {
            config.sub_conf.channels[result.store_id].running = true;
            config.sub_conf.channels[result.store_id].message = result.message;
            config.sub_conf.channels[result.store_id].loading = result.loading;
            window.OrderImportsIndex.refreshLoading(result.store_id);
            window.OrderImportsIndex.pusherSubscription(result.store_id);
        }
    },
    fillOrders: function(result) {
        for (var i = 0, iLength = result.orders.length; i < iLength; i++) {
            // {'items': [data], 'shopify': None, 'name': row[0]}
            var order = result.orders[i];
            for (var j = 0, jLength = order.items.length; j < jLength; j++) {
                // {'key': row[1], 'tracking_number': row[2], 'shopify': None}
                var item = order.items[j],
                    lineItemClass = 'order-'+order.name.replace(/[^\d]+/g, '')+'-line-'+item.key,
                    lineItemSearch = '.'+lineItemClass;

                if (item.identify) {
                    lineItemSearch = lineItemSearch+'[data-identify="'+item.identify+'"]';
                }

                if ($(lineItemSearch).length == 0) {
                    var tr = $('.table .clone').clone();
                } else {
                    var tr = $('.'+lineItemClass);
                }

                tr.find('td:nth-child(1)').text(order.name);
                tr.find('td:nth-child(2)').text(item.key);
                tr.find('td:nth-child(3)').text(item.identify);
                tr.find('td:nth-child(4)').text(item.tracking_number);
                
                var icon = 'fa-times';
                if (item.shopify) {
                    window.OrderImportsIndex.addItem(
                        result.store_id, 
                        order.shopify, 
                        item.shopify, 
                        item.tracking_number
                    );
                    icon = 'fa-check';
                }
                tr.find('td:nth-child(5)').html($('<i class="fa '+icon+'">'));
                
                tr.removeClass('hidden clone');
                tr.addClass(lineItemClass);
                if (item.identify) {
                    tr.attr('data-identify', item.identify);
                }

                if ($(lineItemSearch).length == 0) {
                    $('.table tbody').append(tr);
                }
            }
        }

        window.OrderImportsIndex.saveData();
    },
    addItem: function(store_id, order, item, tracking_number) {
        var found = false;

        if (!this.data[store_id]) {
            this.data[store_id] = [];
        }

        for (var i = 0, iLength = this.data[store_id].length; i < iLength; i++) {
            var storeItem = this.data[store_id][i];
            if (storeItem['order_id'] == order.id && storeItem['line_item_id'] == item.id) {
                storeItem['tracking_number'] = tracking_number;X
                found = true;
                break;
            }
        }

        if (!found) {
            this.data[store_id].push({
                'order_id': order.id, 
                'line_item_id': item.id, 
                'tracking_number': tracking_number
            });
        }
    },
    saveData: function() {
        $('input[name="data"]').val(JSON.stringify(this.data));
        $('input[name="pusher_store_id"]').val($('select[name="stores"] option:selected').attr('data-id'));
    },
    onApproveSubmit: function() {
        $('#approve-form').on('submit', function(e) {
            e.preventDefault();
            $('#approve-button').bootstrapBtn('loading');

            $.ajax({
                type: 'post',
                url: $(this).attr('action'),
                data: $(this).serialize(),
                dataType: 'json',
                success: function(result) {
                    if (result.success) {
                        window.OrderImportsIndex.pusherApproveSubscription();
                    }
                }
            });
        });
    },
    onChangeOnlyOneFilled: function() {
        $('.only-one-filled').on('change', function() {
            if ($(this).val() != '') {
                $(this).parent().siblings(':not(.control-label)').find('input').val('');
            }
        });
    },
    onKeyUpOnlyNumber: function() {
        $('input[type="number"]').on('keydown', function(e) {
            if (e.keyCode == 69) {
                e.preventDefault();
            }
        });
    },
    pusherSubscription: function(storeId) {
        if (typeof(Pusher) === 'undefined') {
            toastr.error('This could be due to using Adblocker extensions<br>' +
                'Please whitelist Shopified App website and reload the page<br>' +
                'Contact us for further assistance',
                'Pusher service is not loaded', {timeOut: 0});
            return;
        }

        var pusher = new Pusher(config.sub_conf.key);
        var channel = pusher.subscribe(config.sub_conf.channels[storeId].hashCode);
        channel.bind('order-import', function(data) {
            if (data.finished) {
                pusher.unsubscribe(config.sub_conf.channels[storeId].hashCode);
                config.sub_conf.channels[storeId].loading = 100;
                window.OrderImportsIndex.refreshLoading(data.store_id);

                if (data.success) {
                    setTimeout(function() {
                        config.sub_conf.channels[storeId].running = false;
                        config.sub_conf.channels[storeId].message = '';

                        window.OrderImportsIndex.ajaxFoundOrders(data.store_id, data.file_index)
                    }, 1000);
                } else {
                    config.sub_conf.channels[storeId].running = false;
                    config.sub_conf.channels[storeId].message = '';
                    window.OrderImportsIndex.refreshLoading(storeId);
                    displayAjaxError('Order Import', data);
                }
            } else {
                config.sub_conf.channels[storeId].message = data.message;
                config.sub_conf.channels[storeId].loading = data.loading;
                window.OrderImportsIndex.refreshLoading(data.store_id);
            }
        });
    },
    pusherApproveSubscription: function() {
        if (typeof(Pusher) === 'undefined') {
            toastr.error('This could be due to using Adblocker extensions<br>' +
                'Please whitelist Shopified App website and reload the page<br>' +
                'Contact us for further assistance',
                'Pusher service is not loaded', {timeOut: 0});
            return;
        }

        var pusher = new Pusher(config.sub_conf.key);
        var storeId = parseInt($('input[name="pusher_store_id"]').val());
        var channel = pusher.subscribe(config.sub_conf.channels[storeId].hashCode);

        channel.bind('order-import-approve', function(data) {
            $('#approve-button').bootstrapBtn('reset');
            if (data.success) {
                pusher.unsubscribe(config.sub_conf.channels[storeId].hashCode);

                setTimeout(function() {
                    $('#order-import-table tbody tr:not(.clone)').remove();

                    var alertEl = $('#approve-alert');
                    if (alertEl.length == 0) {
                        alertEl = $('<div id="approve-alert" class="alert alert-success alert-dismissible fade in">').append(
                            $('<button type="button" class="close" data-dismiss="alert" aria-label="Close">').append(
                                $('<span aria-hidden="true">').text('×')
                            ),
                            'Your orders have been successfuly imported.'
                        );
                    }

                    $('#approve-form').prepend(alertEl);
                }, 1000);
            } else {
                displayAjaxError('Approve Order Import', data);
            }
        });
    },
    refreshLoading: function(storeId) {
        var storeConfig = config.sub_conf.channels[storeId];
        if (storeConfig.running) {
            $('#dropzoneForm .background').css('display', '');
            $('#dropzoneForm .background h5').text(storeConfig.message);
            $('#dropzoneForm .background .progress-bar').css('width', storeConfig.loading + '%');
        } else {
            $('#dropzoneForm .background').css('display', 'none');
        }
    },
    ajaxFoundOrders: function(storeId, fileIndex) {
        $.ajax({
            type: 'GET',
            url: config.ordersImport.urls.found,
            data: {'store': storeId, 'file_index': fileIndex},
            dataType: 'json',
            success: function(result) {
                window.OrderImportsIndex.fillOrders({
                    'orders': result.orders,
                    'store_id': storeId
                });
            },
            complete: function() {
                window.OrderImportsIndex.refreshLoading(storeId);
            }
        });
    }
};

window.OrderImportsIndex.init();
