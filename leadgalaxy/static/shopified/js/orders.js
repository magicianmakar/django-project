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

$(".ignore-error").click(function (e) {
    e.preventDefault();
    var btn = $(this);
    $.ajax({
        url: '/api/ignore-shopify-order-track-errors',
        type: 'POST',
        data:  { id: btn.attr('shopify-order-track-id') },
        success: function (data) {
            if (data.status == 'ok') {
                btn.hide();
                toastr.success('Error Ignored.', 'Order Track');
            } else {
                displayAjaxError('Ignore Error', data);
            }
        },
        error: function (data) {
            displayAjaxError('Ignore Error', data);
        },
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

    ga('clientTracker.send', 'event', 'Order Manual Fulfillment', 'Shopify', sub_conf.shop);

    $.ajax({
        url: api_url('fulfill-order', 'shopify'),
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

    ga('clientTracker.send', 'event', 'Order Filter Toggle', 'Shopify', sub_conf.shop);

    $('#filter-form').toggleClass('active');
});

$("#filter-form").submit(function() {
    var items = $(this).find(":input").filter(function(i, el) {
        if (['desc', 'connected', 'awaiting_order'].includes(el.name) && !$(el).prop('filtred'))  {
            // Note: Update in $('.save-filter-btn').click() too
            el.value = JSON.stringify(el.checked);
            el.checked = true;
            $(el).prop('filtred', true);
        }

        var ret = (((!el.value || el.value.trim().length === 0) &&
                (el.type == 'text' || el.type == 'hidden' || el.type.match(/select/) )) ||
            (el.name == 'sort' && el.value == user_filter.sort) ||
            (el.name == 'sort' && el.value == user_filter.sort) ||
            (el.name == 'desc' && el.value == user_filter.sort_type) ||
            (el.name == 'connected' && el.value == user_filter.connected) ||
            (el.name == 'awaiting_order' && el.value == user_filter.awaiting_order) ||
            (el.name == 'status' && el.value == user_filter.status) ||
            (el.name == 'fulfillment' && el.value == user_filter.fulfillment) ||
            (el.name == 'financial' && el.value == user_filter.financial));

        return ret;
    }).attr("disabled", "disabled");

    return true; // ensure form still submits
});

$('.save-filter-btn').click(function (e) {
    e.preventDefault();

    $("#filter-form").find(":input").filter(function(i, el) {
        if (['desc', 'connected', 'awaiting_order'].includes(el.name) && !$(el).prop('filtred')) {
            el.value = JSON.stringify(el.checked);
            el.checked = true;
            $(el).prop('filtred', true);
        }
    });

    ga('clientTracker.send', 'event', 'Order Save Filter', 'Shopify', sub_conf.shop);

    $.ajax({
        url: api_url('save-orders-filter', 'shopify'),
        type: 'POST',
        data: $('#filter-form').serialize(),
        success: function (data) {
            toastr.success('Orders Filter', 'Saved');
            setTimeout(function() {
                $("#filter-form").trigger('submit');
            }, 1000);
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

            ga('clientTracker.send', 'event', 'Delete Order ID', 'Shopify', sub_conf.shop);
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
                url: api_url('order-fulfill', 'shopify') + '?' + $.param({'order_id': order_id, 'line_id': line_id, }),
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

function placeOrder(e) {
    e.preventDefault();

    var btn = $(e.target);
    btn.button('loading');

    $.ajax({
        url: '/api/order-place',
        type: 'POST',
        data: {
            'store': btn.attr('store'),
            'order_id': btn.attr('order-id'),
            'line_id': btn.attr('line-id'),
        },
    }).done(function(data) {
        swal.close();
        toastr.success('Order successfully placed', 'Order Placed');

    }).fail(function(data) {
        displayAjaxError('Place Order', data);
    }).always(function() {
        btn.button('reset');
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
        url: api_url('order-fulfill', 'shopify'),
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

function showOrderIframe() {
    // $('.order-content-list').removeClass('col-md-12').addClass('col-md-9');
    ///$('.order-content-list-iframe').removeClass('hidden');
}

$(".quick-order-btn").on("click", function(e) {
    e.preventDefault();
    var data_target = $(this).attr("data-target");

    var elObj = $(this).closest("div.order");
    var selected = 0;

    elObj.find('.line-checkbox').each(function (i, el) {
        var isChecked = true;
        if (data_target == "selected") {
            isChecked = el.checked;
        }
        if(isChecked) {
            selected += 1;
            var obj = $(el).closest('div.line');
            var btn= '';
            if ($(obj).hasClass("bundled")) {
                btn = obj.find('a.quick-bundle-order');
            }
            else {
                btn = obj.find('a.place-order');
            }
            btn = $(btn);
            var msg = {
                subject: 'add-order',
                order: {
                    'name': btn.attr('order-name'),
                    'store': btn.attr('store'),
                    'order_id': btn.attr('order-id'),
                    'line_id': btn.attr('line-id'),
                    'order_data': JSON.parse(atob(btn.attr('order-data')))
                },
            };
            document.getElementById('orders-aliexpress-frm').contentWindow.postMessage(JSON.stringify(msg), '*');
        }
    });
    if (selected) {
        showOrderIframe();
        toastr.success("Items added to Queue");
    } else {
        toastr.warning('Please select an item to add to queue');
    }
});

$('.place-order').on('click', function(e) {
    e.preventDefault();

    var btn = $(e.target);
    var msg = {
        subject: 'add-order',
        order: {
            'name': btn.attr('order-name'),
            'store': btn.attr('store'),
            'order_id': btn.attr('order-id'),
            'line_id': btn.attr('line-id'),
            'order_data': JSON.parse(atob(btn.attr('order-data')))

        },
    };

    showOrderIframe();

    document.getElementById('orders-aliexpress-frm').contentWindow.postMessage(JSON.stringify(msg), '*');
    toastr.success("Item added to Queue");
});

window.onmessage = function (e) {
    var message;

    try {
        message = JSON.parse(e.data);
    } catch (e) {
        return;
    }

    if (message && message.subject && message.subject == "show-me") {
        showOrderIframe();
    }
};

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
            url: api_url('order-add-note', 'shopify'),
            type: 'POST',
            data: {
                'order_id': order_id,
                'store': store,
                'note': inputValue
            },
            success: function (data) {
                if (data.status == 'ok') {
                    swal.close();
                    toastr.success('Note added to the order in Shopify.', 'Add Note');
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

$('.note-panel').click(function (e) {
    if ($(this).prop('editing-mode') === true) {
        return;
    } else {
        $(this).prop('editing-mode', true);
        $(this).prop('init-width', $(this).css('width'));
        $(this).prop('init-height', $(this).css('height'));
        $(this).prop('init-overflow', $(this).css('overflow'));
    }

    $(this).animate({
        width: '500px',
        height: '300px',
    }, 300, function() {
        $(this).css('overflow', 'initial');
    });

    $('.edit-note', this).toggle();
    $('.note-preview', this).toggle();
});

$('.note-panel .note-edit-cancel').click(function (e) {
    var parent = $(this).parents('.note-panel');
    parent.animate({
        width: $(parent).prop('init-width'),
        height: $(parent).prop('init-height'),
    }, 300, function() {
        $(parent).css('overflow', $(parent).prop('init-overflow'));
        $(parent).prop('editing-mode', false);
    });

    $('.edit-note', parent).toggle();
    $('.note-preview', parent).toggle();

});

$('.note-panel .note-edit-save').click(function (e) {
    var parent = $(this).parents('.note-panel');
    parent.find('.note-edit-cancel').hide();
    $(this).button('loading');

    var note = $('.edit-note textarea.note', parent).val();
    var order_id = $(this).attr('order-id');
    var store = $(this).attr('store-id');

    ga('clientTracker.send', 'event', 'Edit Order Note', 'Shopify', sub_conf.shop);

    $.ajax({
        url: api_url('order-note', 'shopify'),
        type: 'POST',
        data: {
            'order_id': order_id,
            'store': store,
            'note': note
        },
        context: {btn: this, parent: parent},
        success: function (data) {
            if (data.status == 'ok') {
                toastr.success('Order Note', 'Order note saved in Shopify.');

                // Truncate note
                var maxLength = 70;
                var noteText = note.substr(0, maxLength);
                noteText = noteText.substr(0, Math.min(noteText.length, noteText.lastIndexOf(" ")));
                if (note.length > maxLength) {
                    noteText = noteText+'...';
                }

                $('.note-preview .note-text', this.parent).text(noteText);
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
      return $(el).attr('line-track') || $(el).attr('fulfillment-status') == 'fulfilled' || $(el).attr('excluded-product');
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

    ga('clientTracker.send', 'event', 'Hide Ordered Click', 'Shopify', sub_conf.shop);
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

    ga('clientTracker.send', 'event', 'Hide Non-Connected Click', 'Shopify', sub_conf.shop);
});

/* Connect Product */
$('.add-supplier-btn').click(function (e) {
    e.preventDefault();

    ga('clientTracker.send', 'event', 'Order Add Supplier', 'Shopify', sub_conf.shop);

    $('#modal-supplier-link').prop('shopify-store', $(this).attr('store-id'));
    $('#modal-supplier-link').prop('shopify-product', $(this).attr('shopify-product'));

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
            url: api_url('import-product', 'shopify'),
            type: 'POST',
            data: {
                store: $('#modal-supplier-link').prop('shopify-store'),
                supplier: $('.product-original-link').val(),
                vendor_name: $('.product-supplier-name').val(),
                vendor_url: $('.product-supplier-link').val(),
                product: $('#modal-supplier-link').prop('shopify-product'),
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

$('.cached-img').error(function() {
    $.ajax({
        url: '/api/product-image?' + $.param({
            'store': $(this).attr('store'),
            'product': $(this).attr('product')
        }),
        type: 'DELETE',
        success: function(data) {}
    });
});

$('.line-checkbox').on('ifChanged', function (e) {
    $(this).parents('.line').toggleClass('active', e.target.checked);
});

$('.product-preview img').click(function (e) {
    var checkbox = $(this).parent().find('.line-checkbox');
    if ($(checkbox).prop('disabled')) {
        return;
    }

    checkbox.prop('checked', !checkbox.prop('checked'));
});

$('.help-select').each(function (i, el) {
    $('option', el).each(function (index, option) {
        $(option).attr('title', $(option).text());

        var label = $(option).attr('label') || toTitleCase($(option).val());
        $(option).text(label);
    });

    $(el).change(function (e) {
        var helpTag = $(this).siblings('.help-block');
        $('option', el).each(function (index, option) {
            if ($(option).prop('selected')) {
                helpTag.text($(option).attr('title'));
            }
        });
    });

    $(el).trigger('change');
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
        order.find('.note-panel .note-text').text(data.note_snippet);

        fixNotePanelHeight(order);
    });

    channel.bind('order-sync-status', function(data) {
        var el = $('.order_sync_status');

        if (!el.length) {
            $('.wrapper-content').prepend($('<div class="alert alert-info alert-dismissable">' +
                '<button type="button" class="close" data-dismiss="alert" aria-hidden="true">×</button>' +
                '<i class="fa fa-circle-o-notch fa-spin"></i> Importing ' + data.total + ' orders from your store<span class="order_sync_status"> (0%)</span></div>'));

            el = $('.order_sync_status');
        }

        var progress = ((data.curreny / data.total) * 100.0).toFixed(0);

        el.text(' (' + progress + '%)');

        if (data.curreny >= data.total) {
            el.html('. Sync Completed, <a href="#">reload page</a>').find('a').click(function (e) {
                window.location.reload();
            });

            el.css('font-weight', 'bold').parent().find('i').hide();
        }
    });

    channel.bind('order-risks', function(data) {
        if (sub_conf.order_risk_task && sub_conf.order_risk_task == data.task) {
            for (var order_id in data.orders) {
                var risk_level = data.orders[order_id];
                var el = $('.order-risk-level[order-id=' + order_id +']');

                if (risk_level > 0.7) {
                    el.text('High');
                    el.addClass('badge badge-danger');
                } else if (risk_level > 0.4) {
                    el.text('Medium');
                    el.addClass('badge badge-warning');
                } else {
                    el.text('Low');
                    el.addClass('badge badge-primary');
                }

                if (typeof ($.fn.bootstrapTooltip) === 'undefined') {
                    $(el).tooltip();
                } else {
                    $(el).bootstrapTooltip();
                }
            }
        }
    });

    channel.bind('order-status-update', function(data) {
        $.each(data.orders, function(i, order) {
            var orderEl = $('.order[order-id="' + order.order_id + '"]');
            if (orderEl.length) {
                if (order.line_id) {
                    var lineEl = orderEl.find('.line[line-id=' + order.line_id + ']');
                    // lineEl.find('.order-all').parent().hide();
                    // lineEl.find('.track-details').show();

                    lineEl.find('.place-order').addClass('btn-outline').text(order.status);
                    lineEl.find('.order-line-group').hide();
                }
            }
        });
    });

    channel.bind('track-log-update', function(order) {
        var orderEl = $('.order[order-id="' + order.order_id + '"]');
        if (!orderEl.length) {
            return;
        }

        orderEl.find('.track-details').removeClass('btn-warning btn-info btn-white');

        if (order.seen == 2) {
            orderEl.find('.track-details').addClass('btn-warning');
        } else if (order.seen == 1) {
            orderEl.find('.track-details').addClass('btn-info');
        } else {
            orderEl.find('.track-details').addClass('btn-white');
        }

        orderEl.find('.track-details').text(order.status).show();
    });

    channel.bind('pusher:subscription_succeeded', function() {
        var orders = $(".order-risk-level").map(function() {
            return $(this).attr("order-id");
        }).get();

        if (orders.length) {
            $.ajax({
                url: '/api/order-risks',
                type: 'POST',
                data: JSON.stringify({
                    'store': sub_conf.store,
                    'orders': orders,
                }),
                contentType: "application/json; charset=utf-8",
                dataType: "json",
                success: function(data) {
                    sub_conf.order_risk_task = data.task;
                },
                error: function(data) {
                    displayAjaxError('Failed to Get Order Risks', data);
                }
            });

        }
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

$('.changed-variant').click(function (e) {
    e.preventDefault();

    var btn = $(this);
    btn.button('loading');

    $('#save-variant-change').data('store', $(this).data('store'));
    $('#save-variant-change').data('order', $(this).data('order'));
    $('#save-variant-change').data('line', $(this).data('line'));
    $('#save-variant-change').data('product', $(this).data('product'));
    $('#save-variant-change').data('current-variant', $(this).data('current-variant'));

    $.ajax({
        url: api_url('shopify-variants'),
        type: 'GET',
        data: {
            product: $(this).data('product')
        },
    }).done(function (data) {
        var variant_template = Handlebars.compile($("#variant-change-item-template").html());

        var list = $('.variants-list');
        list.empty();

        $.each(data.variants, function (i, el) {
            list.append(variant_template(el));
        });

        if (btn.data('changed')) {
            list.append(variant_template({
                id: -1,
                title: 'Reset To Customer Selected Variant'
            }));
        }

        ga('clientTracker.send', 'event', 'Change Variant', 'Shopify', sub_conf.shop);

        $('#change-variant-modal').modal('show');

    }).fail(function(data) {
        displayAjaxError('Change Variant', data);
    }).always(function() {
        btn.button('reset');
    });
});

$('#save-variant-change').click(function (e) {
    e.preventDefault();

    var btn = $(this);
    btn.button('loading');

    var variant = $('input[name="new-variant-id"]:checked');
    $.ajax({
        url: api_url('change-order-variant'),
        type: 'POST',
        data: {
            store: $('#save-variant-change').data('store'),
            order: $('#save-variant-change').data('order'),
            line: $('#save-variant-change').data('line'),
            product: $('#save-variant-change').data('product'),
            current_variant: $('#save-variant-change').data('current-variant'),
            remember_variant: $('input[name="remember-variant"]').is(':checked'),
            variant: variant.val(),
            title: variant.attr('title'),
        },
    }).done(function (data) {
        var msg = (variant.attr('title').match('Reset To') ?
            'Variant Reset To Customer Selection' :
            'Variant changed to: ' + variant.attr('title'));

        toastr.success(msg, 'Change Variant');
        $('#change-variant-modal').modal('hide');

        setTimeout(function() {
            window.location.reload();
        }, 500);
    }).fail(function(data) {
        displayAjaxError('Change Variant', data);
    }).always(function() {
        btn.button('reset');
    });
});

$('#orders-audit').on('click', function(e) {
    e.preventDefault();

    window.extensionSendMessage({
        subject: 'GetPageUrl',
        page: 'audit.html',
    }, function(rep) {
        $('#orders-audit-modal .modal-body iframe').remove();
        $('#orders-audit-modal .modal-body').append($('<iframe>'));
        $('#orders-audit-modal').modal('show');
        $('#orders-audit-modal .modal-body iframe').attr('src', rep.url);
    });
});

$(".track-details").click(function(e) {
    var btn = $(e.target);
    var detailsUrl = api_url('track-log') + '?' + $.param({
        'store': btn.attr('store'),
        'order_id': btn.attr('order-id'),
        'line_id': btn.attr('order-id'),
    });

    ga('clientTracker.send', 'event', 'Track Details', 'Shopify', sub_conf.shop);

    $('#modal-tracking-details .modal-content').load(detailsUrl, function(response, status) {
        if (status != 'error') {
            $('#modal-tracking-details').modal('show');
        } else {
            try {
                response = JSON.parse(response);
            } catch (e) {}

            toastr.error(getAjaxError(response));
        }
    });
});

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

    if (window.location.hash.match(/audit/)) {
        window.onExtensionSendMessageReady = function() {
            $('#orders-audit').trigger('click');
        };
    }

    if (window.location.hash.length) {
        window.location.hash = '';
    }

    fixNotePanelHeight();

    $('select#product').select2({
        placeholder: 'Select a Product',
        ajax: {
            url: "/autocomplete/title",
            dataType: 'json',
            delay: 250,
            data: function(params) {
                return {
                    query: params.term, // search term,
                    store: $('#product').data('store'),
                    page: params.page,
                    trunc: 1
                };
            },
            processResults: function(data, params) {
                params.page = params.page || 1;

                return {
                    results: $.map(data.suggestions, function(el) {
                        return {
                            id: el.data,
                            text: el.value,
                            image: el.image,
                        };
                    }),
                    pagination: {
                        more: false
                    }
                };
            },
            cache: true
        },
        escapeMarkup: function(markup) {
            return markup;
        },
        minimumInputLength: 1,
        templateResult: function(repo) {
            if (repo.loading) {
                return repo.text;
            }

            return '<span><img src="' + repo.image + '"><a href="#">' + repo.text.replace('"', '\'') + '</a></span>';
        },
        templateSelection: function(data) {
            return data.text || data.element.innerText;
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

    $('#query_customer').on('change keypress', function (e) {
        var v = $(this).val().trim();

        if (!$('#query_customer_id').length) {
            return;
        }

        if (!v || $('#query_customer_id').attr('orig-value').trim() != v) {
            $('#query_customer_id').val('');
        }
    });

    if ($('#query_customer_id').length) {
        $('#query_customer').autocomplete({
            serviceUrl: '/autocomplete/shopify-customer?' + $.param({
                store: $('#query_customer').data('store')
            }),
            minChars: 1,
            deferRequestBy: 100,
            autoSelectFirst: true,
            noCache: true,
            preventBadQueries: false,
            showNoSuggestionNotice: true,
            noSuggestionNotice: 'No customer found',
            onSelect: function(suggestion) {
                $('#query_customer').val(suggestion.value.replace(/ \([^\)]+\)$/, ''));
                $('#query_customer_id').val(suggestion.data);
                $('#query_customer_id').attr('orig-value', suggestion.data);

                ga('clientTracker.send', 'event', 'Order Autocomplete', 'Customer ID', sub_conf.shop);
            }
        });
    }

    $('#created_at_daterange').daterangepicker({
        format: 'MM/DD/YYYY',
        showDropdowns: true,
        showWeekNumbers: true,
        timePicker: false,
        autoUpdateInput: false,
        ranges: {
            'Today': [moment(), moment()],
            'Yesterday': [moment().subtract(1, 'days'), moment().subtract(1, 'days')],
            'Last 7 Days': [moment().subtract(6, 'days'), moment()],
            'Last 30 Days': [moment().subtract(29, 'days'), moment()],
            'This Month': [moment().startOf('month'), moment().endOf('month')],
            'Last Month': [moment().subtract(1, 'month').startOf('month'), moment().subtract(1, 'month').endOf('month')],
            'All Time': 'all-time',
        },
        opens: 'right',
        drops: 'down',
        buttonClasses: ['btn', 'btn-sm'],
        applyClass: 'btn-primary',
        cancelClass: 'btn-default',
        separator: ' to ',
        locale: {
            applyLabel: 'Submit',
            cancelLabel: 'Clear',
            fromLabel: 'From',
            toLabel: 'To',
            customRangeLabel: 'Custom Range',
            daysOfWeek: ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr','Sa'],
            monthNames: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
            firstDay: 1
        }
    }, function(start, end, label) {
        $('#created_at_daterange span').html(start.format('MMMM D, YYYY') + ' - ' + end.format('MMMM D, YYYY'));
        $('input[name="created_at_daterange"]').val(start.format('MM/DD/YYYY') + '-' + end.format('MM/DD/YYYY'));
    });

    $('#created_at_daterange').on('apply.daterangepicker', function(ev, picker) {
        var start = picker.startDate,
            end = picker.endDate;

        if (start.isValid() && !end.isValid()) {
            end = moment();
        }

        if (start.isValid() && end.isValid()) {
            $('#created_at_daterange span').html(
                start.format(start.year() == moment().year() ? 'MMMM D' : 'MMMM D, YYYY') + ' - ' +
                 end.format(end.year() == moment().year() ? 'MMMM D' : 'MMMM D, YYYY'));
            $('input[name="created_at_daterange"]').val(start.format('MM/DD/YYYY') + '-' + end.format('MM/DD/YYYY'));
        } else {
            $('#created_at_daterange span').html('All Time');
            $('input[name="created_at_daterange"]').val('all');
        }
    });

    $('#created_at_daterange').on('cancel.daterangepicker', function(ev, picker) {
        $('#created_at_daterange span').html('');
        $('input[name="created_at_daterange"]').val('');
    });

    var createdAtDaterangeValue = $('input[name="created_at_daterange"]').val();
    if (createdAtDaterangeValue && createdAtDaterangeValue.indexOf('-') !== -1) {
        var dates = createdAtDaterangeValue.split('-'),
            createdAtStart = moment(dates[0], 'MM/DD/YYYY'),
            createdAtEnd = moment(dates[1], 'MM/DD/YYYY');

        if (createdAtStart.isValid() && !createdAtEnd.isValid()) {
            createdAtEnd = moment();
        }

        $('#created_at_daterange span').html(
            createdAtStart.format(createdAtStart.year() == moment().year() ? 'MMMM D' : 'MMMM D, YYYY') + ' - ' +
            createdAtEnd.format(createdAtEnd.year() == moment().year() ? 'MMMM D' : 'MMMM D, YYYY'));
    }

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
            "mapping": {
                name: 'Variants Mapping'
            },
            "connections": {
                name: 'Product Suppliers'
            },
            "sep1": "---------",
            "dropified": {
                name: 'Open in Dropified'
            },
            "shopify": {
                name: 'Open in Shopify'
            },
        },
        events: {
            show: function(opt) {
                setTimeout(function() {
                    opt.$menu.css({
                        'z-index': '10000',
                        'max-height': '300px',
                        'overflow': 'auto',
                    });
                }, 100);

                return true;
            }
        }
    });

});
})(user_filter, sub_conf);
