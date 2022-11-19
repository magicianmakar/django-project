/* global $, toastr, swal, displayAjaxError, cleanUrlPatch */

(function(user_filter, sub_conf) {
'use strict';
    function addOrderToQueue(order, warn) {

        warn = typeof(warn) !== 'undefined' ? warn : true;
        var autoOrder = $('.order').data('auto-order');
        if (autoOrder === false) {
            toastr.error('Your plan does not support auto ordering.', 'Auto Order not allowed');
            return;
        }

        if (!window.extensionSendMessage) {
            swal('Please Reload the page and make sure you are using the latest version of the extension');
            return;
        }

        window.extensionSendMessage({
            subject: 'AddOrderToQueue',
            from: 'website',
            order: order
        }, function(rep) {
            if (rep && rep.error == 'alread_in_queue' && warn) {
                toastr.error('Product is already in Orders Queue');
            }
        });
    }

    function orderBundle(order_data_id, order_name, store_type, fail_callback) {
        fail_callback = typeof(fail_callback) !== 'undefined' ? fail_callback : function(data) {};

        $.ajax({
            url: api_url('order-data', window.storeType),
            type: 'GET',
            data: {
                order: order_data_id
            },
        }).done(function(data) {
            if (!data.is_bundle) {
                return displayAjaxError('Order Bundle', 'Not a bundle order');
            }

            var order = {
                cart: true,
                bundle: true,
                items: []
            };

            $.each(data.products, function(i, product) {
                order.items.push({
                    url: product.order_url,
                    order_data: order_data_id,
                    order_name: order_name,
                    order_id: data.order_id,
                    line_id: data.line_id,
                    line_title: product.title,
                    supplier_type: product.supplier_type,
                    store_type: store_type,
                    product: product,
                });
            });

            if (order.items.length > 0) {
                order.order_data = order_data_id;
                order.order_name = order.items[0].order_name;
                order.order_id = order.items[0].order_id;
                order.supplier_type = order.items[0].supplier_type;
                order.store_type = order.items[0].store_type;

                order.line_id = $.map(order.items, function(el) {
                    return el.line_id;
                });

                order.line_title = '<ul style="padding:0px;overflow-x:hidden;">';

                order.line_title += $.map(order.items.slice(0, 3), function(el) {
                    return '<li>&bull; ' + el.line_title + '</li>';
                }).join('');

                if (order.items.length > 3) {
                    var extra_count = order.items.length - 3;
                    order.line_title += '<li>&bull; Plus ' + (extra_count) + ' Product' + (extra_count > 1 ? 's' : '') + '...</li>';
                }

                order.line_title += '</ul>';

            }

            addOrderToQueue(order);

            if (!window.storeType || window.storeType === 'shopify') {
                ga('clientTracker.send', 'event', 'Ordered Bundle', 'Shopify', sub_conf.shop);
            }

        }).fail(fail_callback);
    }

    function orderItems(current_order, supplier_type, exclude_lines) {
        supplier_type = typeof(supplier_type) !== 'undefined' ? supplier_type : null;
        exclude_lines = typeof(exclude_lines) !== 'undefined' ? exclude_lines : false;

        var items = {alibaba: []};
        var order = {
            cart: true,
            items: []
        };

        var orderBundles = 0;

        // Ordering by supplier doesn't show order selected items, so we intrinsically add
        if (current_order.find('.line-checkbox:checked').length > 0) {
            if (supplier_type) {
                exclude_lines = true;
                current_order.find('.line-checkbox').each(function (i, el) {
                    if(!el.checked) {
                        $(el).parents('.line').attr('exclude', 'true');
                    } else {
                        $(el).parents('.line').attr('exclude', 'false');
                    }
                });

            }
        } else {
            current_order.find('.line').attr('exclude', '');
        }

        $('.line', current_order).each(function(i, el) {
            if (exclude_lines) {
                // Check if we should exclude this line if "exclude" attribute is "true"
                if ($(el).attr('exclude') === 'true') {
                    return;
                }
            }

            var itemSupplier = $(el).attr('supplier-type');
            if (supplier_type) {
                // If Supplier type (Aliexpress/eBay) doesn't match exclude this item
                if (itemSupplier !== supplier_type) {
                    return;
                }
            }

            if (itemSupplier === 'alibaba') {
                items.alibaba.push($(el).attr('order-data-id'));
                return;
            }

            if ($(el).attr('line-data') && !$(el).attr('line-track')) {
                if ($(el).hasClass('bundled') && $(el).attr('supplier-type') != 'alibaba') {
                    var bundleBtn = $('.order-bundle', el);
                    var order_data_id = bundleBtn.attr('order-data');
                    var order_name = bundleBtn.attr('order-number');
                    var store_type = bundleBtn.attr('store-type');

                    orderBundle(order_data_id, order_name, store_type, function(data) {
                        toastr.error(data, 'Order Bundle');
                    });
                    orderBundles++;
                } else {
                    order.items.push({
                        url: $('.add-to-cart', el).data('href') || $('.add-to-cart', el).prop('href'),
                        order_data: $(el).attr('order-data-id'),
                        order_name: $(el).attr('order-number'),
                        order_id: $(el).attr('order-id'),
                        line_id: $(el).attr('line-id'),
                        line_title: $(el).attr('line-title'),
                        supplier_type: $(el).attr('supplier-type'),
                    });
                }
            }
        });

        if (order.items.length) {
            order.order_data = order.items[0].order_data.replace(/_[^_]+$/, '');
            order.order_name = order.items[0].order_name;
            order.order_id = order.items[0].order_id;
            order.supplier_type = order.items[0].supplier_type;

            order.line_id = $.map(order.items, function(el) {
                return el.line_id;
            });

            order.line_title = '<ul style="padding:0px;overflow-x:hidden;">';

            order.line_title += $.map(order.items.slice(0, 3), function(el) {
                return '<li>&bull; ' + el.line_title +'</li>';
            }).join('');

            if (order.items.length > 3) {
                var extra_count = order.items.length - 3;
                order.line_title += '<li>&bull; Plus ' + (extra_count) +' Product' + (extra_count > 1 ? 's' : '') + '...</li>';
            }

            order.line_title += '</ul>';

            addOrderToQueue(order);

        } else if (items.alibaba.length > 0) {
            orderItemsAlibaba(items.alibaba);

        } else {
            var addressTxt = $('.line', current_order).parent().parent().contents('.shipping-info').contents('div').first().text();
            addressTxt = addressTxt.replace(/[,]/gm,'').trim();
            if (addressTxt === 'N/A' || !addressTxt.length) {
                toastr.error('Invalid Shipping address', 'No items to order');
                return;
            }

            if (orderBundles === 0) {
                toastr.error('The items have been ordered or are not connected', 'No items to order');
            }
        }
    }

    $('.order-by-supplier').on('click', function() {
        var addTextSelected = function(button) {
            if (button.text().indexOf('Selected') === -1) {
                button.text('Selected ' + button.text());
            }
        };
        var removeTextSelected = function(button) {
            if (button.text().indexOf('Selected') !== -1) {
                button.text(button.text().replace('Selected ', ''));
            }
        };

        var hasSelected = $(this).parents('.order').find('.line-checkbox:checked').length > 0;
        $(this).next('.dropdown-menu').find('.order-seleted-suppliers').each(function() {
            if (hasSelected) {
                addTextSelected($(this));
            } else {
                removeTextSelected($(this));
            }
        });
    });

    $('.order-seleted-lines').click(function (e) {
        e.preventDefault();

        var order = $(this).parents('.order');
        var selected = 0;

        order.find('.line-checkbox').each(function (i, el) {
            if(!el.checked) {
                $(el).parents('.line').attr('exclude', 'true');
            } else {
                selected += 1;
                $(el).parents('.line').attr('exclude', 'false');
            }
        });

        orderItems(order, null, true);

        if (!window.storeType || window.storeType === 'shopify') {
            ga('clientTracker.send', 'event', 'Ordered Selected Items', 'Shopify', sub_conf.shop);
        }
    });

    $('.order-seleted-suppliers').click(function(e) {
        e.preventDefault();

        var order = $(this).parents('.order');
        var supplier_type = $(this).attr('supplier-type');
        var selected = 0;

        order.find('.line').each(function(i, el) {
            if ($(el).attr('supplier-type') === supplier_type) {
                selected += 1;
            }
        });

        if (!selected) {
            swal('Order From Supplier', 'This order doesn\'t have item from the selected supplier\n' +
                'Please reload the page and try again', 'warning');
            return;
        }

        orderItems(order, supplier_type);

        ga('clientTracker.send', 'event', 'Ordered Selected Supplier', 'Shopify', sub_conf.shop);
    });

    $('.order-items').on('click', function(e) {
        e.preventDefault();
        var order = $(this).parents('.order');

        orderItems(order, null, true);
    });

    $('.order-bundle').click(function(e) {
        e.preventDefault();

        var order_data_id = $(e.target).attr('order-data');
        var order_name = $(e.target).attr('order-number');
        var store_type = $(e.target).attr('store-type');

        orderBundle(order_data_id, order_name, store_type, function(data) {
            displayAjaxError('Order Bundle', data);
        });
    });

    $('.queue-order-btn').click(function(e) {
        e.preventDefault();
        var btn = $(e.target);
        var group = btn.parents('.order-line-group');

        var line = $(this).parents('.line');
        if (line && line.attr('supplier-type') === 'alibaba') {
            orderItemsAlibaba([line.attr('order-data-id')]);
            return;
        }

        addOrderToQueue({
            url: btn.data('href'),
            order_data: group.attr('order-data-id'),
            order_name: group.attr('order-number'),
            order_id: group.attr('order-id'),
            line_id: group.attr('line-id'),
            line_title: group.attr('line-title'),
            supplier_type: group.attr('supplier-type'),
        });
    });


    $('.quick-quick-ext-btn').click(function(e) {
        e.preventDefault();
        var btn = $(e.target);
        var group = btn.parents('.order-line-group');
        var order_variant = btn.data('variant');
        var order_productid = btn.data('productid');
        var order_quantity = btn.data('quantity');
        var orderdataid = btn.data('orderdataid');

        var line = $(this).parents('.line');
        if (line && line.attr('supplier-type') === 'alibaba') {
            orderItemsAlibaba([line.attr('order-data-id')]);
            return;
        }

        // Admitad
        if (window.admitad_site_id && order_productid){
            generate_admitad_click('https://www.aliexpress.com/item/' + order_productid + '.html',window.app_base_link);
        }

        // sending message to extension to fetch product data
        var order_data = {
            url: btn.data('href'),
            order_data: group.attr('order-data-id'),
            order_name: group.attr('order-number'),
            order_id: group.attr('order-id'),
            line_id: group.attr('line-id'),
            line_title: group.attr('line-title'),
            supplier_type: group.attr('supplier-type'),
        };
        var skuIdStr = false;

        window.extensionSendMessage({
            subject: 'getVariantsCombinations',
            from: 'website',
            url: btn.data('producturl')
        }, function(rep) {
            rep.forEach(function(item) {

                if (item.skuAttr == "" &&  order_variant == "") {
                    skuIdStr = item.skuIdStr;
                    return false;
                }

                var variants = item.skuAttr.split(';');
                var variants_normalized = [];
                variants.forEach(function(variant){
                    var variant_title=variant.split("#");

                    // replace empty "ships from" labels
                    if (variant_title[0]=='200007763:201336100') {
                        variant_title[1]='China';
                    }
                    if (variant_title[0]=='200007763:201336106') {
                        variant_title[1]='United States';
                    }

                    var variant_title_normalized=variant_title[1].trim();
                    variants_normalized.push(variant_title_normalized);
                });
                var variants_normalized_str = variants_normalized.join(' / ');
                if (variants_normalized_str.toLowerCase().trim() == order_variant.toLowerCase().trim()) {
                    skuIdStr = item.skuIdStr;
                    return false;
                }
            });

            if (skuIdStr) {
                order_data['url']+='&quick-order=1&objectId='+
                    order_productid+'&skuId='+skuIdStr+'&quantity='+order_quantity;
                addOrderToQueue(order_data);
            }
            else {
                toastr.error('Quick Order Error (Product variants can\'t be auto-detected. Please use regular ordering method.' ) ;
            }

        });
    });


    $('.auto-shipping-btn').click(function (e) {
        e.preventDefault();

        var btn = $(e.target);
        var group = btn.parents('.order-line-group');

        $('#shipping-modal').prop('data-href', $(this).data('href'));
        $('#shipping-modal').prop('data-order', $(this).attr('data-order'));

        var shippingParams = {
            'id': $(this).attr('original-id'),
            'product': $(this).attr('product-id'),
            'country': $(this).attr('country-code'),
            'type': $(group).attr('supplier-type'),
            'zip_code': btn.parents('.order').find('.zip-code').text(),
            'for': 'order'
        };
        if (window.storeType) {
            shippingParams[window.storeType] = '1';
        }
        var url = '/shipping/info?' + $.param(shippingParams);

        $('#shipping-modal .shipping-info').load(url, function (response, status, xhr) {
            if (xhr.status != 200) {
                displayAjaxError('Shipping Method', 'Server Error, Please try again.');
                return;
            }

            $('#shipping-modal').modal('show');

            $('#shipping-modal .shipping-info tbody tr').click(function (e) {
                e.preventDefault();

                var url = $('#shipping-modal').prop('data-href').trim();
                if (url.indexOf('?') !== -1) {
                    if (!url.match(/[\\?&]$/)) {
                        url += '&';
                    }
                } else {
                    url += '?';
                }

                url = url + $.param({
                    SAPlaceOrder: $('#shipping-modal').prop('data-order'),
                    SACompany: $(this).attr('company'),  // company
                    SACountry: $(this).attr('country')   // country_code
                });

                addOrderToQueue({
                    url: url,
                    order_data: group.attr('order-data-id'),
                    order_name: group.attr('order-number'),
                    order_id: group.attr('order-id'),
                    line_id: group.attr('line-id'),
                    line_title: group.attr('line-title'),
                });

                $('#shipping-modal').modal('hide');

                $('#shipping-modal').prop('data-href', null);
                $('#shipping-modal').prop('data-order', null);
            }).css({
                'cursor': 'pointer',
                'height': '35px'
            }).find('td').css({
                'padding': '0 10px',
                'vertical-align': 'middle'
            });
        });
    });
})(user_filter, sub_conf);
