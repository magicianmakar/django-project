window.OrderImportsIndex = {
    data: {},
	init: function() {
        this.setDropzoneOptions();
    },
    setDropzoneOptions: function() {
        Dropzone.options.dropzoneForm = {
            paramName: "file", // The name that will be used to transfer the file
            maxFilesize: 2, // MB
            uploadMultiple: false,
            dictDefaultMessage: "<strong>Drop files here or click to upload. </strong></br> (After the file is dropped or selected, it will be sent to the server.)",
            acceptedFiles: '.csv',
            init: function() {
                this.on("processing", function(file) {
                    this.options.url = $('select[name="stores"]').val();
                });

                this.on("success", window.OrderImportsIndex.onDropzoneSuccess);
            }
        };
    },
    onDropzoneSuccess: function(file, result) {
        for (var i = 0, iLength = result.orders.length; i < iLength; i++) {
            // {'items': [data], 'shopify': None, 'name': row[0]}
            var order = result.orders[i];
            for (var j = 0, jLength = order.items.length; j < jLength; j++) {
                // {'key': row[1], 'tracking_number': row[2], 'shopify': None}
                var item = order.items[j],
                    lineItemClass = 'order-'+order.name.replace(/[^\d]+/g, '')+'-line-'+item.key;

                if ($('.'+lineItemClass).length == 0) {
                    var tr = $('.table .clone').clone();
                } else {
                    var tr = $('.'+lineItemClass);
                }

                tr.find('td:nth-child(1)').text(order.name);
                tr.find('td:nth-child(2)').text(item.key);
                tr.find('td:nth-child(3)').text(item.tracking_number);
                
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
                tr.find('td:nth-child(4)').html($('<i class="fa '+icon+'">'));
                
                tr.removeClass('hidden clone');
                tr.addClass(lineItemClass);
                if ($('.'+lineItemClass).length == 0) {
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
                storeItem['tracking_number'] = tracking_number;
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
    }
};

window.OrderImportsIndex.init();