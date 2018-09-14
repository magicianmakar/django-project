/* global $, toastr, swal, displayAjaxError, cleanUrlPatch */

(function(user_filter, sub_conf, product_variants) {
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

    $.ajax({
        url: '/api/fulfill-order',
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
    Cookies.set('orders_filter', !$('.filter-form').is(':visible'));

    if (!$('.filter-form').is(':visible')) {
        $('.filter-form').fadeIn('fast');
    } else {
        $('.filter-form').fadeOut('fast');
    }
});

$(".filter-form").submit(function() {
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
    }).attr("disabled", "disabled").css('background-color', '#fff');

    setTimeout(function() {
        items.removeAttr('disabled');
    }, 100);

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
        url: '/api/save-orders-filter',
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
    var line_id = btn.attr('line-id');
    var html = '<ul>';
    html += '<li style="list-style:none">Aliexpress Order ID: <a target="_blank" ' +
        'href="http://trade.aliexpress.com/order_detail.htm?orderId=' + source_id + '">' + source_id + '</a></li>';
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
        closeOnConfirm: false,
        showLoaderOnConfirm: true,
    },
    function(isConfirm) {
        if (isConfirm) {
            $.ajax({
                url: '/api/order-fulfill' + '?' + $.param({'order_id': order_id, 'line_id': line_id, }),
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

    swal({
        title: "Place Order",
        text: "Do you want to order this item?",
        type: "warning",
        showCancelButton: true,
        closeOnConfirm: false,
        showLoaderOnConfirm: true,
        confirmButtonText: "Place Order",
        animation: "slide-from-top",
    }, function() {
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
            toastr.success('Item was ordered.', 'Order Placed');
            // btn.hide();

        }).fail(function(data) {
            displayAjaxError('Place Order', data);
        });
    });
}

function addOrderSourceID(e) {
    e.preventDefault();
    var btn = $(e.target);

    var orderData = {
        order_id: btn.attr('order-id'),
        line_id: btn.attr('line-id'),
        store: btn.attr('store'),
        btn: btn
    };

    swal({
        title: "Order Placed",
        text: "Aliexpress Order ID:",
        type: "input",
        showCancelButton: true,
        closeOnConfirm: false,
        animation: "slide-from-top",
        inputPlaceholder: "Order ID",
        showLoaderOnConfirm: true
    }, function(inputValue) {
        if (inputValue === false) return false;
        inputValue = inputValue.trim();

        if (inputValue === "") {
            swal.showInputError("You need to enter an Order ID.");
            return false;
        }

        var order_link = inputValue.match(/orderId=([0-9]+)/);
        if (order_link && order_link.length == 2) {
            inputValue = order_link[1];
        }

        if (inputValue.length === 0) {
            swal.showInputError("The entered Order ID is not valid.");
            return false;
        }

        addOrderSourceRequest({
            'store': orderData.store,
            'order_id': orderData.order_id,
            'line_id': orderData.line_id,
            'aliexpress_order_id': inputValue,
        });
    });
}

function addOrderSourceRequest(data_api) {
    $.ajax({
        url: '/api/order-fulfill',
        type: 'POST',
        data: data_api,
        context: {
            data_api: data_api
        },
    }).done(function(data) {
        if (data.status == 'ok') {
            swal.close();
            toastr.success('Item was marked as ordered in Dropified.', 'Marked as Ordered');
        } else {
            displayAjaxError('Mark as Ordered', data);
        }
    }).fail(function(data) {
        var error = getAjaxError(data);
        var api = $.extend({}, this.data_api, {forced: true});

        if (error.indexOf('linked to an other Order') != -1) {
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
                    }
                });
        } else {
            displayAjaxError('Mark as Ordered', data);
        }
    });
}

$('.mark-as-ordered').click(addOrderSourceID);
$('.place-order').click(placeOrder);

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
            url: '/api/order-add-note',
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

    $.ajax({
        url: '/api/order-note',
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

function addOrderToQueue(order, warn) {
    warn = typeof(warn) !== 'undefined' ? warn : true;

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
        'for': 'order'
    }), function (response, status, xhr) {
        if (xhr.status != 200) {
            displayAjaxError('Shiping Method', 'Server Error, Please try again.');
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
            url: '/api/import-product',
            type: 'POST',
            data: {
                store: $('#modal-supplier-link').prop('shopify-store'),
                supplier: $('.product-original-link').val(),
                vendor_name: $('.product-supplier-name').val(),
                vendor_url: $('.product-supplier-link').val(),
                product: $('#modal-supplier-link').prop('shopify-product'),
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

$('.product-preview img').click(function (e) {
    var checkbox = $(this).parent().find('.line-checkbox');
    checkbox.prop('checked', !checkbox.prop('checked'));
});

$('.order-seleted-lines').click(function (e) {
    e.preventDefault();

    var order = $(this).parents('.order');
    var delete_lines = [];
    var selected = 0;

    order.find('.line-checkbox').each(function (i, el) {
        if(!el.checked) {
            delete_lines.push($(el).parents('.line'));
        } else {
            selected += 1;
        }
    });

    if(selected <= 1) {
        swal('Order Selected', 'Please Select at least 2 items to order', 'warning');
        return;
    } else {
        $.each(delete_lines, function (i, el) {
            $(el).remove();
        });
    }

    order.find('.order-all').trigger('click');
});

$('.help-select').each(function (i, el) {
    $('option', el).each(function (index, option) {
        $(option).attr('title', $(option).text());

        var label = $(option).attr('label') || toTitleCase($(option).val());
        $(option).text(label);
    });

    $(el).change(function (e) {
        var helpTag = $(this).parents('.row').find('.help-block');
        $('option', el).each(function (index, option) {
            if ($(option).prop('selected')) {
                helpTag.text($(option).attr('title'));
            }
        });
    });

    $(el).trigger('change');
});

function fetchOrdersToQueue(data) {
    var bulkOrdersFound = 0;
    var api_url = /^http/.test(data) ? data : cleanUrlPatch(window.location.href);
    var api_data = /^http/.test(data) ? null : data;
    $.ajax({
        url: api_url,
        type: 'GET',
        data: api_data,
        success: function(data) {
            var pbar = $('#bulk-order-modal .progress .progress-bar');
            var page = parseInt(pbar.attr('current')) + 1;
            var pmax = parseInt(pbar.attr('max'));
            pbar.css('width', ((page * 100.0) / pmax) + '%')
                .text(page + ' Page' + (page > 1 ? 's' : ''))
                .attr('current', page);

            $.each(data.orders, function (i, order) {
                window.ordersQueueData.push(order);
            });

            if (data.next && !window.bulkOrderStop) {
                fetchOrdersToQueue(data.next);
            } else {
                window.bulkOrderStop = false;

                $('.stop-bulk-btn').button('reset');
                $('#bulk-order-modal').modal('hide');

                if (window.ordersQueueData.length) {
                    swal({
                        title: 'Bulk Orders Processing',
                        text: 'You have ' + window.ordersQueueData.length + ' Order' +
                              (window.ordersQueueData.length ? 's' : '') + ' that need to be fulfilled',
                        type: "success",
                        showCancelButton: true,
                        animation: false,
                        cancelButtonText: "Cancel",
                        confirmButtonText: 'Continue',
                        closeOnCancel: true,
                        closeOnConfirm: false,
                        showLoaderOnConfirm: true,
                    },
                    function(isConfirm) {
                        if (isConfirm) {
                            $.each(window.ordersQueueData, function (i, order) {
                                addOrderToQueue(order, false);
                            });

                            swal.close();
                        }
                    });
                } else {
                    swal({
                        title: 'Bulk Orders Processing',
                        text: 'No order has been found!',
                        type: "warning"
                    });
                }
            }
        },
        error: function(data) {
            displayAjaxError('Bulk Order Processing', data);
        }
    });
}

$('.bulk-order-btn').click(function (e) {
    e.preventDefault();

    var orders_count = parseInt($(e.target).attr('orders-count'));
    if (!orders_count) {
        swal({
            title: 'No orders found',
            text: 'Try adjusting your current Filters',
            type: "warning",
        });

        return;
    }

    window.ordersQueueData = [];

    $('#bulk-order-modal .progress .progress-bar').css('width', '0px');
    $('#bulk-order-modal .progress .progress-bar').attr('max', $(e.target).attr('pages-count'));
    $('#bulk-order-modal .progress .progress-bar').attr('current', '0');

    $('#bulk-order-modal').modal({
        backdrop: 'static',
        keyboard: false
    });

    var formData = $('form.filter-form').serializeArray();
    formData.push({
        name: 'bulk_queue',
        value: '1',
    });

    fetchOrdersToQueue(formData);
});

$('.stop-bulk-btn').click(function (e) {
    e.preventDefault();

    window.bulkOrderStop = true;
    $(e.target).button('loading');
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

    channel.bind('product-price-trends', function(data) {
        if (sub_conf.product_price_trends_task && sub_conf.product_price_trends_task == data.task) {
            for (var i = 0; i < data.trends.length; i++) {
                var item = data.trends[i];
                var target = $('.price-trends[data-product=' + item.product + '][data-variant=' + item.variant + ']');
                $(target).find('a').attr('href', '/product/' + item.product + '#alerts');

                if (item.trend == 'asc') {
                    $(target).find('i').addClass('fa-caret-up price-up');
                } else if (item.trend == 'desc') {
                    $(target).find('i').addClass('fa-caret-down price-down');
                }

                $(target).show();
            }
        }
    });

    channel.bind('order-status-update', function(data) {
        $.each(data.orders, function (i, order) {
            var orderEl = $('.order[order-id="' + order.order_id + '"]');
            if (!orderEl.length) {
                return;
            }

            if (!orderEl.hasClass('disabled')) {
                orderEl.find('.place-order').button('loading');
            }

            setTimeout(function () {
                orderEl.find('.place-order').text(order.status);
            }, 100);
        });
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

        if (product_variants.length) {
            $.ajax({
                url: '/api/product-price-trends',
                type: 'POST',
                data: JSON.stringify({
                    'store': sub_conf.store,
                    'product_variants': product_variants,
                }),
                contentType: "application/json; charset=utf-8",
                dataType: "json",
                success: function(data) {
                    sub_conf.product_price_trends_task = data.task;
                },
                error: function(data) {
                    displayAjaxError('Failed to Get Product Price Trends', data);
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

        if (start.isValid && !end.isValid()) {
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

        if (createdAtStart.isValid && !createdAtEnd.isValid()) {
            createdAtEnd = moment();
        }

        $('#created_at_daterange span').html(
            createdAtStart.format(createdAtStart.year() == moment().year() ? 'MMMM D' : 'MMMM D, YYYY') + ' - ' +
            createdAtEnd.format(createdAtEnd.year() == moment().year() ? 'MMMM D' : 'MMMM D, YYYY'));
    }

    setTimeout(function() {
        window.location.reload();
    }, 3500 * 1000);

});
})(user_filter, sub_conf, product_variants);
