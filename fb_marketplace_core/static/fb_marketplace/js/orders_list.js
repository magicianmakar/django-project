/* global $, toastr, swal, displayAjaxError, cleanUrlPatch */

(function(user_filter, sub_conf) {
'use strict';

var placed_order_interval = {};

$(function () {
    $(".itooltip").tooltip();
});

$(".more-info").click(function (e) {
    e.preventDefault();

    var element = $(this).find('i');
    var target = $(this).parents('tr').next();

    target.toggle('fade', function() {
        if (target.is(":visible")) {
            element.removeClass('fa-plus');
            element.addClass('fa-minus');
        } else {
            element.removeClass('fa-minus');
            element.addClass('fa-plus');
        }
    });
});

$('.fulfill-btn').click(function (e) {
    $('#modal-fulfillment form').trigger('reset');

    $('#modal-fulfillment #fulfill-order-id').val($(this).attr('order-id'));
    $('#modal-fulfillment #fulfill-line-id').val($(this).attr('line-id'));
    $('#modal-fulfillment #fulfill-store').val($(this).attr('store'));
    $('#modal-fulfillment #fulfill-traking-number').val($(this).attr('tracking-number'));

    if ($(this).prop('fulfilled')) {
        return;
    }

    if(localStorage.fulfill_notify_customer && !$('#fulfill-notify-customer').prop('initialized')) {
        $('#fulfill-notify-customer').val(localStorage.fulfill_notify_customer);
        $('#fulfill-notify-customer').prop('initialized', true);
    }

    $('#modal-fulfillment').modal('show');
});

$('#fullfill-order-btn').click(function (e) {
    e.preventDefault();

    localStorage.fulfill_notify_customer = $('#fulfill-notify-customer').val();

    $(this).button('loading');
    var line_btn = $('.fulfill-btn[line-id="'+$('#modal-fulfillment #fulfill-line-id').val()+'"]');

    ga('clientTracker.send', 'event', 'Order Manual Fulfillment', 'fb_marketplace', sub_conf.shop);

    $.ajax({
        url: api_url('fulfill-order', 'fb_marketplace'),
        type: 'POST',
        data:  $('#modal-fulfillment form').serialize(),
        context: {btn: $(this), line: line_btn},
        success: function (data) {
            if (data.status == 'ok') {
                $('#modal-fulfillment').modal('hide');
                this.line.prop('fulfilled', true);

                swal.close();
                toastr.success('Fulfillment Status changed to Fulfilled.', 'Fulfillment Status');
            } else {
                displayAjaxError('Fulfill Order', data);
            }
        },
        error: function (data) {
            displayAjaxError('Fulfill Order', data);
        },
        complete: function () {
            this.btn.button('reset');

            var btn = this.line;
            setTimeout(function() {
                if (btn.prop('fulfilled')) {
                    btn.removeClass('btn-default');
                    btn.addClass('btn-success');
                    btn.text('Fulfilled');
                }
            }, 100);
        }
    });
});

$('.filter-btn').click(function (e) {
    Cookies.set('orders_filter', !$('#filter-form').hasClass('active'));

    ga('clientTracker.send', 'event', 'Order Filter Toggle', 'fb_marketplace', sub_conf.shop);

    $('#filter-form').toggleClass('active');
});

$('#query_input').change(function (e) {
    var val = $(e.target).val();

    $('#query').val(val && val.indexOf('@') !== -1 ? 'b:' + btoa(val) : val);
});

$(".filter-form form").submit(function() {
    var items = $(this).find(":input").filter(function(i, el) {
        if (['desc', 'connected', 'awaiting_order'].includes(el.name) && !$(el).prop('filtred'))  {
            // Note: Update in $('.save-filter-btn').click() too
            el.value = JSON.stringify(el.checked);
            el.checked = true;
            $(el).prop('filtred', true);
        }

        var ret = (((!el.value || el.value.trim().length === 0) &&
                (el.type == 'text' || el.type == 'hidden' || el.type.match(/select/))));

        return ret;
    }).attr("disabled", "disabled").css('background-color', '#fff');

    setTimeout(function() {
        items.removeAttr('disabled');
    }, 100);

    return true; // ensure form still submits
});

$('.save-filter-btn').click(function (e) {
    e.preventDefault();

    $(".filter-form form").find(":input").filter(function(i, el) {
        if (['desc', 'connected', 'awaiting_order'].includes(el.name) && !$(el).prop('filtred')) {
            el.value = JSON.stringify(el.checked);
            el.checked = true;
            $(el).prop('filtred', true);
        }
    });

    ga('clientTracker.send', 'event', 'Order Save Filter', 'fb_marketplace', sub_conf.shop);

    $.ajax({
        url: api_url('save-orders-filter', 'fb_marketplace'),
        type: 'POST',
        data: $('.filter-form form').serialize(),
        success: function (data) {
            toastr.success('Orders Filter', 'Saved');
            // setTimeout(function() {
            //     $(".filter-form").trigger('submit');
            // }, 1000);
        },
        error: function (data) {
            displayAjaxError('Orders Filter', data);
        }
    });
});

function toTitleCase(str) {
    return str.replace('_', ' ').replace(/\w\S*/g, function(txt){return txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase();});
}

$('.expand-btn').click(function (e) {
    $(".more-info").trigger('click');
});

function confirmDeleteOrderID(e) {
    e.preventDefault();

    var btn = $(e.target);

    var tr_parent = btn.parents('tr').first();
    var order_id = btn.attr('order-id');
    var source_id = btn.attr('source-order-id');
    var source_url = btn.attr('source-url');
    var line_id = btn.attr('line-id');
    var html = '<ul>';
    html += '<li style="list-style:none">Supplier Order ID: <a target="_blank" ' +
        'href="' + source_url + '">' + source_id + '</a></li>';
    html += '<li style="list-style:none">Order date: ' + btn.attr('order-date') + '</li>';
    html += '</ul';

    swal({
        title: '',
        text: html,
        showCancelButton: true,
        html: true,
        animation:false,
        cancelButtonText: "Close",
        confirmButtonText: 'Delete Order ID',
        confirmButtonColor: "#DD6B55",
        closeOnCancel: true,
        closeOnConfirm: false,
    },
    function(isConfirm) {
        if (isConfirm) {
            deleteOrderID(tr_parent, order_id, line_id);

            ga('clientTracker.send', 'event', 'Delete Order ID', 'fb_marketplace', sub_conf.shop);
        }
    });
}

$('.placed-order-details').click(confirmDeleteOrderID);

function deleteOrderID(tr_parent, order_id, line_id) {
    swal({
        title: 'Delete Order ID',
        text: 'Are you sure you want to delete the Order ID?',
        type: "warning",
        showCancelButton: true,
        animation: false,
        cancelButtonText: "Cancel",
        confirmButtonText: 'Yes',
        confirmButtonColor: "#DD6B55",
        closeOnCancel: true,
        closeOnConfirm: true,
    },
    function(isConfirm) {
        if (isConfirm) {
            $.ajax({
                url: api_url('order-fulfill', 'fb_marketplace') + '?' + $.param({'order_id': order_id, 'line_id': line_id, }),
                type: 'DELETE',
                context: {tr: tr_parent},
                success: function (data) {
                    if (data.status == 'ok') {
                        toastr.success('Note: The Order ID has not been removed from the order notes.', 'Order ID has been deleted');
                        swal.close();
                        $(this.tr).removeClass('success');
                    } else {
                        displayAjaxError('Delete Order ID', data);
                    }
                },
                error: function (data) {
                    displayAjaxError('Delete Order ID', data);
                }
            });
        }
    });
}

$('#modal-add-order-id .supplier-type').on('change', function (e) {
    var supplierType = $(e.target).val();
    var placeholder = '';

    if (supplierType === 'ebay') {
        placeholder = 'https://www.ebay.com/vod/FetchOrderDetails?itemid=XXXX&transId=XXXX';
    } else if (supplierType === 'aliexpress') {
        placeholder = 'https://trade.aliexpress.com/order_detail.htm?orderId=XXXX';
    } else if (supplierType === 'dropified-print') {
        placeholder = 'P12345';
    } else if (supplierType === 'supplements') {
        placeholder = 'Payment ID from your supplement payments page';
    } else {
        placeholder = '';
    }

    $('#modal-add-order-id .order-id').attr('placeholder', placeholder);
    $('#modal-add-order-id .order-id').focus();
});

$('#modal-add-order-id').on('shown.bs.modal', function() {
    $(this).find('input.order-id').trigger('focus');
});

$('#modal-add-order-id form').on('submit', function (e) {
    e.preventDefault();

    var btn = $(this).find('.save-order-id-btn');

    var orderData = $('#modal-add-order-id').data('order');

    var supplierType = $('#modal-add-order-id .supplier-type').val();
    var orderId = $('#modal-add-order-id .order-id').val().trim();

    if (!orderId) {
        swal('Add Order ID', 'You need to enter a valid Order ID or Url', 'error');
        return;
    }

    var callback = function(success) {
        if (success) {
            $('#modal-add-order-id').modal('hide');
        }

        btn.button('reset');
    };

    ga('clientTracker.send', 'event', 'Add Order ID', supplierType, sub_conf.shop);

    if (['aliexpress', 'alibaba', 'other', 'supplements'].indexOf(supplierType) > -1) {
        var order_link = orderId.match(/orderId=([0-9]+)/);
        if (supplierType !== 'other' && order_link && order_link.length == 2) {
            orderId = order_link[1];
        }

        btn.button('loading');

        addOrderSourceRequest({
            'store': orderData.store,
            'order_id': orderData.order_id,
            'line_id': orderData.line_id,
            'source_type': supplierType,
            'aliexpress_order_id': orderId,
        }, callback);

    } else if (supplierType === 'ebay') {
        if (!orderId.match('^https?://')) {
            swal('Add Order ID', 'Please enter Order Url For eBay orders', 'error');
            return;
        }

        btn.button('loading');

        window.extensionSendMessage({
            subject: 'getEbayOrderId',
            url: orderId,
        }, function (data) {
            if (data && data.purchaseOrderId) {
                addOrderSourceRequest({
                    'store': orderData.store,
                    'order_id': orderData.order_id,
                    'line_id': orderData.line_id,
                    'source_type': supplierType,
                    'aliexpress_order_id': data.purchaseOrderId,
                }, callback);

            } else {
                swal('Could not get eBay Order ID');
            }
        });
    } else if (supplierType === 'dropified-print') {
        btn.button('loading');

        addOrderSourceRequest({
            'store': orderData.store,
            'order_id': orderData.order_id,
            'line_id': orderData.line_id,
            'source_type': supplierType,
            'aliexpress_order_id': orderId,
        }, function(success) {
            if (success) {
                $('#modal-add-order-id').modal('hide');
                connectDropifiedPrintOrder(orderId);
            }

            btn.button('reset');
        });
    }
});

function addOrderSourceID(e) {
    e.preventDefault();
    var btn = $(e.target);

    var orderData = {
        order_id: btn.attr('order-id'),
        line_id: btn.attr('line-id'),
        store: btn.attr('store'),
        supplier_type: btn.parents('.line').attr('supplier-type'),
    };

    $('#modal-add-order-id').data('order', orderData);

    $('#modal-add-order-id .supplier-type').val(orderData.supplier_type);
    $('#modal-add-order-id .supplier-type').trigger('change');
    $('#modal-add-order-id .order-id').val('');
    $('#modal-add-order-id .save-order-id-btn').button('reset');

    $('#modal-add-order-id').modal('show');
}

function addOrderSourceRequest(data_api, callback) {
    callback = typeof(callback) === 'undefined' ? function() {} : callback;

    $.ajax({
        url: api_url('order-fulfill', 'fb_marketplace'),
        type: 'POST',
        data: data_api,
        context: {
            data_api: data_api
        },
    }).done(function(data) {
        if (data.status == 'ok') {
            swal.close();
            toastr.success('Item was marked as ordered in Dropified.', 'Marked as Ordered');

            callback(true);
        } else {
            displayAjaxError('Mark as Ordered', data);

            callback(false);
        }
    }).fail(function(data) {
        var error = getAjaxError(data);
        var api = $.extend({}, this.data_api, {forced: true});

        if (data.status == 409) {
            swal({
                    title: 'Duplicate Order ID',
                    text: error + '\nAre you sure you want to add it to this order too?',
                    type: "warning",
                    showCancelButton: true,
                    animation: false,
                    cancelButtonText: "Cancel",
                    confirmButtonText: 'Yes',
                    confirmButtonColor: "#DD6B55",
                    closeOnCancel: true,
                    closeOnConfirm: false,
                    showLoaderOnConfirm: true,
                },
                function(isConfirm) {
                    if (isConfirm) {
                        addOrderSourceRequest(api, callback);
                    } else {
                        callback(false);
                    }
                });
        } else {
            displayAjaxError('Mark as Ordered', data);
            callback(false);
        }
    });
}

$('.mark-as-ordered').click(addOrderSourceID);

$('.add-order-note').click(function (e) {
    e.preventDefault();

    var order_id = $(this).attr('order-id');
    var store = $(this).attr('store');

    swal({
        title: "Add Note",
        text: "Append note to this order notes:",
        type: "input",
        showCancelButton: true,
        closeOnConfirm: false,
        animation: "slide-from-top",
        inputPlaceholder: "Notes",
        showLoaderOnConfirm: true
    }, function(inputValue) {
        if (inputValue === false) return false;
        if (inputValue === "") {
            swal.showInputError("You need to enter a note.");
            return false;
        }

        $.ajax({
            url: api_url('order-add-note', 'fb_marketplace'),
            type: 'POST',
            data: {
                'order_id': order_id,
                'store': store,
                'note': inputValue
            },
            success: function (data) {
                if (data.status == 'ok') {
                    swal.close();
                    toastr.success('Note added to the order in fb_marketplace.', 'Add Note');
                } else {
                    displayAjaxError('Add Note', data);
                }
            },
            error: function (data) {
                displayAjaxError('Add Note', data);
            },
            complete: function () {
            }
        });
    });
});

$('.view-order-notes').click(function (e) {
    e.preventDefault();

    swal({
        title: '',
        text: atob($(this).attr('notes')),
        type: '',
        animation: 'none'
    });
});

$('.note-panel .note-preview').click(function (e) {
    var parent = $(this).parents('.note-panel');
    $('.edit-note', parent).toggleClass('hidden');
    $('.note-preview', parent).toggleClass('hidden');
});

$('.note-panel .note-edit-cancel').click(function (e) {
    var parent = $(this).parents('.note-panel');
    $('.edit-note', parent).toggleClass('hidden');
    $('.note-preview', parent).toggleClass('hidden');
});

$('.note-panel .note-edit-save').click(function (e) {
    var parent = $(this).parents('.note-panel');
    parent.find('.note-edit-cancel').hide();
    $(this).button('loading');

    var note = $('.edit-note textarea.note', parent).val();
    var order_id = $(this).attr('order-id');
    var store = $(this).attr('store-id');

    ga('clientTracker.send', 'event', 'Edit Order Note', 'fb_marketplace', sub_conf.shop);

    $.ajax({
        url: api_url('order-note', 'fb_marketplace'),
        type: 'POST',
        data: {
            'order_id': order_id,
            'store': store,
            'note': note
        },
        context: {btn: this, parent: parent},
        success: function (data) {
            if (data.status == 'ok') {
                toastr.success('Order Note', 'Order note saved in fb_marketplace.');
                $('.note-preview .note-text', this.parent).text(note);
            } else {
                displayAjaxError('Add Note', data);
            }
        },
        error: function (data) {
            displayAjaxError('Add Note', data);
        },
        complete: function () {
            $(this.btn).button('reset');
            $('.note-edit-cancel', this.parent).show().trigger('click');
        }
    });
});

function findMarkedLines() {
    $('.fulfillment-status button.status-orderd-btn').remove();

    $('.var-info table tr[class="success"]').each(function (i, tr) {
        var orderTR = $(tr).parents('tr').prev();
        orderTR.find('.fulfillment-status').append(
            $('<button class="btn btn-info btn-circle btn-xs itooltip no-outline status-orderd-btn" '+
                'type="button" title="Order with lines marked as Ordered"><i class="fa fa-check"></i></button>'
                ).click(function (e) {
                $(this).parents('tr').find('.more-info').trigger('click');
            })
        );
    });

    $(".itooltip").tooltip();
}

function updateOrderedStatus(line) {
    var order = $(line).parents('.order');

    var ordered = order.find('.line').filter(function (i, el) {
      return $(el).attr('line-track') || $(el).attr('fulfillment-status') == 'fulfilled';
    }).length;

    var order_items = order.find('.line').length;
    var order_status = order.find('.order-status');

    if (ordered === 0) {
        order_status.html('<span class="badge badge-danger primary">&nbsp;</span> No Products Ordered');
    } else if (ordered != order_items) {
        order_status.html('<span class="badge badge-warning primary">&nbsp;</span> Partially Ordered');
    } else {
        order_status.html('<span class="badge badge-primary completed-order">&nbsp;</span> Order Complete');
    }
}

function fixNotePanelHeight(order) {
    order = typeof(order) === 'undefined' ? document : order;
    $('.note-panel', order).each(function(i, el) {
        if ($(el).prop('editing-mode')) {
            $(el).prop('init-height', $(el).parents('.shipping-info').outerHeight() + 'px');
        } else {
            $(el).css({
                height: $(el).parents('.shipping-info').outerHeight() + 'px',
                overflow: 'hidden'
            });
        }
    });
}

$('.hide-ordered-btn').click(function () {
    $('.completed-order').parents('.order').toggle();

    $(this).toggleClass('hidded');

    if ($(this).hasClass('hidded')) {
        $(this).text('Show Ordered');

        $('.pagination a').each(function (i, el) {
            var url = $(el).attr('href');
            var hash = 'hide-compete';
            if (url.indexOf(hash)==-1) {
                if (!url.match(/#/)) {
                    hash = '#' + hash;
                } else if (url.match(/#[a-z]+/)) {
                    hash = ';' + hash;
                }

                $(el).attr('href', url+hash);
            }
        });
    } else {
        $(this).text('Hide Ordered');

        $('.pagination a').each(function (i, el) {
            var url = $(el).attr('href');
            var hash = 'hide-compete';
            if (url.indexOf(hash)!=-1) {
                $(el).attr('href', url.replace(hash, '').replace(/#+;*/, '#'));
            }
        });
    }

    ga('clientTracker.send', 'event', 'Hide Ordered Click', 'fb_marketplace', sub_conf.shop);
});

$('.hide-non-connected-btn').click(function () {
    $('.order[connected="0"]').toggle();

    $(this).toggleClass('hidded');

    if ($(this).hasClass('hidded')) {
        $(this).text('Show Non Connected');

        $('.pagination a').each(function (i, el) {
            var url = $(el).attr('href');
            var hash = 'hide-non-connected';
            if (url.indexOf(hash)==-1) {
                if (!url.match(/#/)) {
                    hash = '#' + hash;
                } else if (url.match(/#[a-z]+/)) {
                    hash = ';' + hash;
                }

                $(el).attr('href', url+hash);
            }
        });
    } else {
        $(this).text('Hide Non Connected');

        $('.pagination a').each(function (i, el) {
            var url = $(el).attr('href');
            var hash = 'hide-non-connected';
            if (url.indexOf(hash)!=-1) {
                $(el).attr('href', url.replace(hash, '').replace(/#+;*/, '#'));
            }
        });
    }

    ga('clientTracker.send', 'event', 'Hide Non-Connected Click', 'fb_marketplace', sub_conf.shop);
});

/* Connect Product */
$('.add-supplier-btn').click(function (e) {
    e.preventDefault();

    ga('clientTracker.send', 'event', 'Order Add Supplier', 'fb_marketplace', sub_conf.shop);

    $('#modal-supplier-link').prop('fb_marketplace-store', $(this).attr('store-id'));
    $('#modal-supplier-link').prop('fb_marketplace-product', $(this).attr('fb_marketplace-product'));

    $('#modal-supplier-link').modal('show');
});


$('.product-original-link').bindWithDelay('keyup', function (e) {
    var input = $(e.target);
    var parent = input.parents('.product-export-form');
    var product_url = input.val().trim();

    renderSupplierInfo(product_url, parent);
}, 200);

$('.add-supplier-info-btn').click(function (e) {
    e.preventDefault();

    $.ajax({
            url: api_url('import-product', 'fb_marketplace'),
            type: 'POST',
            data: {
                store: $('#modal-supplier-link').prop('fb_marketplace-store'),
                supplier: $('.product-original-link').val(),
                vendor_name: $('.product-supplier-name').val(),
                vendor_url: $('.product-supplier-link').val(),
                product: $('#modal-supplier-link').prop('fb_marketplace-product'),
                from: 'orders'
            },
        }).done(function (data) {
            toastr.success('Product is Connected!', 'Product Connect');

            $('#modal-supplier-link').modal('hide');

            setTimeout(function() {
                window.location.reload();
            }, 1500);
        }).fail(function(data) {
            displayAjaxError('Product Connect', data);
        }).always(function() {
        });
});

/* /Connect Product */

$('.product-preview img').click(function (e) {
    var checkbox = $(this).parent().find('.line-checkbox');
    checkbox.prop('checked', !checkbox.prop('checked'));
});

$('#country-filter').chosen({
    search_contains: true,
    width: '100%'
});

function pusherSub() {
    if (typeof(Pusher) === 'undefined') {
        toastr.error('This could be due to using Adblocker extensions<br>' +
            'Please whitelist Dropified website and reload the page<br>' +
            'Contact us for further assistance',
            'Pusher service is not loaded', {timeOut: 0});
        return;
    }

    var pusher = new Pusher(sub_conf.key);
    var channel = pusher.subscribe(sub_conf.channel);

    channel.bind('order-source-id-add', function(data) {
        var line = $('.line[line-id="' + data.line_id + '"]');
        if (!line.length) {
            return;
        }

        line.attr('line-track', data.track);
        line.find('.line-order-id').find('a').remove();
        line.find('.line-order-id').append($('<a>', {
            'class': 'placed-order-details',
            'text': '#' + String(data.source_id).split(',').join(' #'),
            'order-id': data.order_id,
            'line-id': data.line_id,
            'source-order-id': data.source_id,
            'source-url': data.source_url,
            'order-date': 'Few minutes ago'
        }).click(confirmDeleteOrderID));

        line.find('.line-ordered .badge').removeClass('badge-danger').addClass('badge-primary');
        line.find('.line-ordered .ordered-status').text('Order Placed');
        line.find('.line-tracking').empty();

        updateOrderedStatus(line);
        findMarkedLines();
    });

    channel.bind('order-source-id-delete', function(data) {
        var line = $('.line[line-id="' + data.line_id + '"]');
        if (!line.length) {
            return;
        }

        line.attr('line-track', '');
        line.find('.line-order-id').find('a').remove();
        line.find('.line-order-id').append($('<a>', {
            'class': 'mark-as-ordered',
            'text': 'Add Supplier ID',
            'order-id': data.order_id,
            'line-id': data.line_id,
            'store': data.store_id,
        }).click(addOrderSourceID));

        line.find('.line-ordered .badge').addClass('badge-danger').removeClass('badge-primary');
        line.find('.line-ordered .ordered-status').text('Not ordered');
        line.find('.line-tracking').empty();

        updateOrderedStatus(line);
        findMarkedLines();
    });

    channel.bind('order-note-update', function(data) {
        var order = $('.order[order-id="' + data.order_id + '"]');
        if (!order.length) {
            return;
        }

        order.find('.note-panel textarea').val(data.note);
        order.find('.note-panel .note-text').text(data.note);

        fixNotePanelHeight(order);
    });

    /*
    pusher.connection.bind('disconnected', function () {
        toastr.warning('Please reload the page', 'Disconnected', {timeOut: 0});
    });

    channel.bind('pusher:subscription_error', function(status) {
        toastr.warning('Please reload the page', 'Disconnected', {timeOut: 0});
    });
    */
}

$(function () {
    if (Cookies.get('orders_filter') == 'true') {
        $('#filter-form').addClass('active');
    }

    pusherSub();
    findMarkedLines();

    if (window.location.hash.match(/hide-compete/)) {
        $('.hide-ordered-btn').trigger('click');
    }

    if (window.location.hash.match(/hide-non-connected/)) {
        $('.hide-non-connected-btn').trigger('click');
    }

    if (window.location.hash.length) {
        window.location.hash = '';
    }

    $('#query_input').trigger('change');

    fixNotePanelHeight();
/*
    $('#product_title').keyup(function() {
        if (!$(this).val().trim().length) {
            $('input[name="product"]', $(this).parent()).val('');
        }
    }).autocomplete({
        serviceUrl: '/autocomplete/title?' + $.param({store: $('#product_title').data('store')}),
        minChars: 1,
        deferRequestBy: 1000,
        onSelect: function(suggestion) {
            $('input[name="product"]', $(this).parent()).val(suggestion.data);
        }
    });

    $('#supplier_name').autocomplete({
        serviceUrl: '/autocomplete/supplier-name?' + $.param({store: $('#supplier_name').data('store')}),
        minChars: 1,
        deferRequestBy: 1000,
        onSelect: function(suggestion) {
            $('#supplier_name').val(suggestion.value);
            ga('clientTracker.send', 'event', 'Order Autocomplete', 'Supplier', sub_conf.shop);
        }
    });

    $('#shipping_method_name').autocomplete({
        serviceUrl: '/autocomplete/shipping-method-name?' + $.param({store: $('#shipping_method_name').data('store')}),
        minChars: 1,
        deferRequestBy: 1000,
        onSelect: function(suggestion) {
            $('#shipping_method_name').val(suggestion.value);
            ga('clientTracker.send', 'event', 'Order Autocomplete', 'Shipping Method', sub_conf.shop);
        }
    });
*/

    $.contextMenu({
        selector: '.open-product-in',
        trigger: 'left',
        callback: function(key, options) {
            var link = options.$trigger.data('link-' + key);
            if (link) {
                window.open(link, '_blank');

                ga('clientTracker.send', 'event', 'Order ContextMenu', key, sub_conf.shop);
            }
        },
        items: {
            "mapping": {name: 'Variants Mapping'},
            "connections": {name: 'Product Suppliers'},
            "sep1": "---------",
            "dropified": {name: 'Open in Dropified'},
            "store": {name: 'Open in fb_marketplace'},
        },
        events: {
            show: function(opt) {
                setTimeout(function() {
                    opt.$menu.css({'z-index': '10000', 'max-height': '300px', 'overflow': 'auto'});
                }, 100);

                return true;
            }
        }
    });

    setupDateRangePicker('#created_at_daterange', 'input[name="created_at_daterange"]', true);
});
})(user_filter, sub_conf);
