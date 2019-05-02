/* global $, toastr, swal, displayAjaxError */

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

$('#fulfill-provider-name').prop('disabled', true);

$('#fulfill-provider').change(function(e) {
    var value = $(this).find('option:selected').text();
    if (value == 'Custom Provider') {
        $('#fulfill-provider-name').prop('disabled', false);
    } else {
        $('#fulfill-provider-name').prop('disabled', true);
    }
});

$('.fulfill-btn').click(function (e) {
    $('#modal-fulfillment form').trigger('reset');

    $('#modal-fulfillment #fulfill-order-id').val($(this).attr('order-id'));
    $('#modal-fulfillment #fulfill-line-id').val($(this).attr('line-id'));
    $('#modal-fulfillment #fulfill-store').val($(this).attr('store'));
    $('#modal-fulfillment #fulfill-product-id').val($(this).attr('product-id'));
    $('#modal-fulfillment #fulfill-tracking-number').val($(this).attr('tracking-number'));

    if ($(this).prop('fulfilled')) {
        return;
    }

    if(localStorage.fulfill_notify_customer && !$('#fulfill-notify-customer').prop('initialized')) {
        var notifyCustomer = localStorage.fulfill_notify_customer == 'yes' ? 'yes' : 'no';
        $('#fulfill-notify-customer').val(notifyCustomer);
        $('#fulfill-notify-customer').prop('initialized', true);
    }

    $('#modal-fulfillment').modal('show');
});

$('#fullfill-order-btn').click(function (e) {
    e.preventDefault();
    localStorage.fulfill_notify_customer = $('#fulfill-notify-customer').val();
    $(this).button('loading');

    var orderId = $('#modal-fulfillment #fulfill-order-id').val();
    var lineId = $('#modal-fulfillment #fulfill-product-id').val();

    $.ajax({
        url: api_url('fulfill-order', 'gkart'),
        type: 'POST',
        data:  $('#modal-fulfillment form').serialize(),
        context: {btn: $(this), orderId: orderId, lineId: lineId},
        success: function (data) {
            if (data.status == 'ok') {
                $('#modal-fulfillment').modal('hide');
                swal.close();
                toastr.success('Fulfillment Status changed to Fulfilled.', 'Fulfillment Status');

                // Replace button with fulfilled button
                var $newButton = $('<span/>').addClass('label label-success').html('Fulfilled');
                $('#fulfill-line-btn-' + this.orderId + '-' + this.lineId).html($newButton);

                var $order = $('#order_' + this.orderId);

                // Increment placed orders by one
                var placedOrders = parseInt($order.data('placed-orders')) + 1;
                $order.data('placed-orders', placedOrders);

                var linesCount = parseInt($order.data('lines-count'));

                var $orderStatus = $('#fulfillment-status-order-' + this.orderId);
                var $newStatus = $('<span/>').addClass('badge badge-primary');

                if (placedOrders == linesCount) {
                    $newStatus.html('Fulfilled');
                } else {
                    $newStatus.html('Partially Fulfilled');
                }

                // Update order status
                $orderStatus.html($newStatus);
            } else {
                displayAjaxError('Fulfill Order', data);
            }
        },
        error: function (data) {
            displayAjaxError('Fulfill Order', data);
        },
        complete: function () {
            this.btn.button('reset');
        }
    });
});

$('.filter-btn').click(function (e) {
    Cookies.set('orders_filter', !$('.filter-form').is(':visible'));

    if (!$('.filter-form').is(':visible')) {
        $('.filter-form').fadeIn('fast');
    } else {
        $('.filter-form').fadeOut('fast');
    }
});

$(".filter-form").submit(function() {
    $(this).find(":input").filter(function(i, el) {
        if (['desc', 'connected', 'awaiting_order'].includes(el.name) && !$(el).prop('filtred'))  {
            // Note: Update in $('.save-filter-btn').click() too
            el.value = JSON.stringify(el.checked);
            el.checked = true;
            $(el).prop('filtred', true);
        }

        var ret = (((!el.value || el.value.trim().length === 0) &&
                (el.type == 'text' || el.type == 'hidden' || el.type.match(/select/))));

        return ret;
    }).attr("disabled", "disabled");
    return true; // ensure form still submits
});

$('.save-filter-btn').click(function (e) {
    e.preventDefault();

    $(".filter-form").find(":input").filter(function(i, el) {
        if (['desc', 'connected', 'awaiting_order'].includes(el.name) && !$(el).prop('filtred')) {
            el.value = JSON.stringify(el.checked);
            el.checked = true;
            $(el).prop('filtred', true);
        }
    });

    $.ajax({
        url: api_url('save-orders-filter', 'gkart'),
        type: 'POST',
        data: $('.filter-form').serialize(),
        success: function (data) {
            toastr.success('Orders Filter', 'Saved');
            setTimeout(function() {
                $(".filter-form").trigger('submit');
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
                url: api_url('order-fulfill', 'gkart') + '?' + $.param({'order_id': order_id, 'line_id': line_id, }),
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

$('#modal-add-order-id form').submit(function(e) {
    e.preventDefault();
    $('#modal-add-order-id .save-order-id-btn').trigger('click');
});

$('#modal-add-order-id .save-order-id-btn').click(function (e) {
    e.preventDefault();

    var btn = $(e.target);

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

    if (supplierType === 'aliexpress') {
        var order_link = orderId.match(/orderId=([0-9]+)/);
        if (order_link && order_link.length == 2) {
            orderId = order_link[1];
        }

        btn.button('loading');

        addOrderSourceRequest({
            'store': orderData.store,
            'order_id': orderData.order_id,
            'line_id': orderData.line_id,
            'source_type': orderData.supplier_type,
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
                    'source_type': orderData.supplier_type,
                    'aliexpress_order_id': data.purchaseOrderId,
                }, callback);
            } else {
                swal('Could not get eBay Order ID');
            }
        });
    }
});

function addOrderSourceID(e) {
    e.preventDefault();
    var btn = $(e.target);

    var orderData = {
        order_id: btn.attr('order-id'),
        line_id: btn.attr('product-id'),
        store: btn.attr('store'),
        supplier_type: btn.parents('.line').attr('supplier-type'),
    };

    $('#modal-add-order-id').data('order', orderData);

    $('#modal-add-order-id .supplier-type').val(orderData.supplier_type);
    $('#modal-add-order-id .order-id').val('');
    $('#modal-add-order-id .save-order-id-btn').button('reset')

    $('#modal-add-order-id').modal('show');
}

function addOrderSourceRequest(data_api, callback) {
    callback = typeof(callback) === 'undefined' ? function() {} : callback;

    $.ajax({
        url: api_url('order-fulfill', 'gkart'),
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
                        addOrderSourceRequest(api);
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

function addOrderNote(orderId, note) {
    var lastSpace, notePreview = note, maxLength = 70;

    if (note.length > maxLength) {
        notePreview = note.substr(0, maxLength);
        lastSpace = notePreview.lastIndexOf(' ');
        if (lastSpace > 0) {
            notePreview = notePreview.substr(0, Math.min(notePreview.length, lastSpace));
        }
        notePreview += '...';
    }

    $('#order_' + orderId).find('span.note-text').html(notePreview);
    $('#order_' + orderId).find('textarea.note').html(note);
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
            url: api_url('order-add-note', 'gkart'),
            type: 'POST',
            data: {
                'order_id': order_id,
                'store': store,
                'note': inputValue
            },
            success: function (data) {
                if (data.status == 'ok') {
                    swal.close();
                    toastr.success('Note added to the order in GrooveKart store.', 'Add Note');
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

    $.ajax({
        url: api_url('order-note', 'gkart'),
        type: 'POST',
        data: {
            'order_id': order_id,
            'store': store,
            'note': note
        },
        context: {btn: this, parent: parent},
        success: function (data) {
            if (data.status == 'ok') {
                toastr.success('Order Note', 'Order note saved in GrooveKart store.');
                addOrderNote(order_id, note);
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
            console.log(el)
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
            console.log(el)
            var url = $(el).attr('href');
            var hash = 'hide-compete';
            if (url.indexOf(hash)!=-1) {
                $(el).attr('href', url.replace(hash, '').replace(/#+;*/, '#'));
            }
        });
    }
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
});

function addOrderToQueue(order) {
    window.extensionSendMessage({
        subject: 'getVersion',
        from: 'website',
    }, function(rep) {
        if (rep && rep.version) {
            if (versionCompare('1.71.0', rep.version) <= 0) {
                // New Version that support Ordes Queue
                window.extensionSendMessage({
                    subject: 'AddOrderToQueue',
                    from: 'website',
                    order: order
                }, function(rep) {
                    if (rep && rep.error == 'alread_in_queue') {
                        toastr.error('Product is already in Orders Queue');
                    }
                });
            } else {
                window.extensionSendMessage({
                    subject: 'InitOrderAll',
                    url: order.url
                }, function(rep) {});

                setTimeout(function () {
                    window.extensionSendMessage({
                        subject: 'OpenWindowUrl',
                        url: order.url
                    }, function(rep) {});
                }, 100);
            }
        } else {
            swal('Please Reload the page and make sure you are using the latest version of the extension');
        }
    });
}
$('.queue-order-btn').click(function(e) {
    e.preventDefault();
    var btn = $(e.target);
    var group = btn.parents('.order-line-group');

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

$('.auto-shipping-btn').click(function (e) {
    e.preventDefault();

    var btn = $(e.target);
    var group = btn.parents('.order-line-group');

    $('#shipping-modal').prop('data-href', $(this).data('href'));
    $('#shipping-modal').prop('data-order', $(this).attr('data-order'));

    $('#shipping-modal .shipping-info').load('/shipping/info?' + $.param({
        'id': $(this).attr('original-id'),
        'product': $(this).attr('product-id'),
        'country': $(this).attr('country-code'),
        'type': $(group).attr('supplier-type'),
        'for': 'order',
        'gkart': 1,
    }), function (response, status, xhr) {
        if (xhr.status != 200) {
            displayAjaxError('Shipping Method', 'Server Error, Please try again.');
            return;
        }

        $('#shipping-modal').modal('show');

        $('#shipping-modal .shipping-info tbody tr')
            .click(function (e) {
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
            })
            .css({cursor: 'pointer', height: '35px'})
            .find('td').css({'padding': '0 10px', 'vertical-align': 'middle'});
    });

});

/* Connect Product */
$('.add-supplier-btn').click(function (e) {
    e.preventDefault();
    $('#modal-supplier-link').prop('gkart-store', $(this).attr('store-id'));
    $('#modal-supplier-link').prop('gkart-product', $(this).attr('gkart-product'));

    $('#modal-supplier-link').modal('show');
});

$('.product-original-link').bindWithDelay('keyup', function (e) {
    var input = $(e.target);
    var parent = input.parents('.product-export-form');
    var product_url = input.val().trim();

    if(!product_url.length || !(/aliexpress.com/i).test(product_url)) {
        return;
    }

    var product_id = product_url.match(/[\/_]([0-9]+)\.html/);
    if(product_id.length != 2) {
        return;
    } else {
        product_id = product_id[1];
    }

    $('.product-original-link-loading', parent).show();

    window.extensionSendMessage({
        subject: 'ProductStoreInfo',
        product: product_id,
    }, function(rep) {
        $('.product-original-link-loading', parent).hide();

        if (rep && rep.name) {
            $('.product-supplier-name', parent).val(rep.name);
            $('.product-supplier-link', parent).val(rep.url);
        }
    });
}, 200);

$('.add-supplier-info-btn').click(function (e) {
    e.preventDefault();

    $.ajax({
            url: api_url('import-product', 'gkart'),
            type: 'POST',
            data: {
                store: $('#modal-supplier-link').prop('gkart-store'),
                supplier: $('.product-original-link').val(),
                vendor_name: $('.product-supplier-name').val(),
                vendor_url: $('.product-supplier-link').val(),
                product: $('#modal-supplier-link').prop('gkart-product'),
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

/*$('.cached-img').error(function() {
    $.ajax({
        url: api_url('product-image', 'gkart') + '?' + $.param({
            'store': $(this).attr('store'),
            'product': $(this).attr('product')
        }),
        type: 'DELETE',
        success: function(data) {}
    });
});*/

$('.product-preview img').click(function (e) {
    var checkbox = $(this).parent().find('.line-checkbox');
    checkbox.prop('checked', !checkbox.prop('checked'));
});

function orderItems(current_order, supplier_type, exclude_lines) {
    supplier_type = typeof(supplier_type) !== 'undefined' ? supplier_type : null;
    exclude_lines = typeof(exclude_lines) !== 'undefined' ? exclude_lines : false;

    var order = {
        cart: true,
        items: []
    };

    $('.line', current_order).each(function(i, el) {
        if (exclude_lines) {
            // Check if we should exclude this line if "exclude" attribute is "true"
            if ($(el).attr('exclude') === 'true') {
                return;
            }
        }

        if (supplier_type) {
            // If Supplier type (Aliexpress/eBay) doesn't match exclude this item
            if ($(el).attr('supplier-type') !== supplier_type) {
                return;
            }
        }

        if ($(el).attr('line-data') && !$(el).attr('line-track')) {
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
    });

    if (order.items.length === 1) {
        // If it's a single item, add it as a single order
        var item = order.items[0];
        item.url = item.url.replace(/(SAStep|SACart)=[a-z]+/g, '').replace(/\?&&/, '?');

        addOrderToQueue(item);

    } else if (order.items.length > 1) {
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
    } else {
        toastr.error('The items have been ordered or are not connected', 'No items to order');
    }
}

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

    if(selected <= 1) {
        swal('Order Selected', 'Please Select at least 2 items to order', 'warning');
        return;
    }

    orderItems(order, null, true);
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
            'text': '#' + data.source_id.split(',').join(' #'),
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
            'text': 'Add',
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
        $('.filter-form').show();
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
        }
    });

    $('#shipping_method_name').autocomplete({
        serviceUrl: '/autocomplete/shipping-method-name?' + $.param({store: $('#shipping_method_name').data('store')}),
        minChars: 1,
        deferRequestBy: 1000,
        onSelect: function(suggestion) {
            $('#shipping_method_name').val(suggestion.value);
        }
    });
*/
    setTimeout(function() {
        window.location.reload();
    }, 3500 * 1000);
});
})(user_filter, sub_conf);
