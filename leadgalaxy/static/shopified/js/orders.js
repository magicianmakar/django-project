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
    $(this).find(":input").filter(function(i, el) {
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
            toastr.success('Item was marked as ordered in Shopified App.', 'Marked as Ordered');
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
        url: btn.prop('href'),
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

    $('#shipping-modal').prop('data-href', $(this).prop('href'));
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

$('#country-filter').chosen({
    search_contains: true,
    width: '100%'
});

function pusherSub() {
    if (typeof(Pusher) === 'undefined') {
        toastr.error('This could be due to using Adblocker extensions<br>' +
            'Please whitelist Shopified App website and reload the page<br>' +
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
            'text': '#' + data.source_id,
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

        var progress = ((data.curreny / data.total) * 100.0).toFixed(0);

        el.text(' (' + progress + '%)');

        if (data.curreny >= data.total) {
            el.html('. Sync Completed, <a href="#">reload page</a>').find('a').click(function (e) {
                window.location.reload();
            });

            el.css('font-weight', 'bold').parent().find('i').hide();
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

    // $('#product_title').keyup(function() {
    //     if (!$(this).val().trim().length) {
    //         $('input[name="product"]', $(this).parent()).val('');
    //     }
    // }).autocomplete({
    //     serviceUrl: '/autocomplete/title?' + $.param({store: $('#product_title').data('store')}),
    //     minChars: 1,
    //     deferRequestBy: 1000,
    //     onSelect: function(suggestion) {
    //         $('input[name="product"]', $(this).parent()).val(suggestion.data);
    //     }
    // });

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
            'Last Month': [moment().subtract(1, 'month').startOf('month'), moment().subtract(1, 'month').endOf('month')]
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
        $('input[name="created_at_daterange"]').val(start.format('MM/DD/YYYY') + '-' + end.format('MM/DD/YYYY'))
    });

    $('#created_at_daterange').on('apply.daterangepicker', function(ev, picker) {
        var start = picker.startDate,
            end = picker.endDate;

        $('#created_at_daterange span').html(start.format('MMMM D, YYYY') + ' - ' + end.format('MMMM D, YYYY'));
        $('input[name="created_at_daterange"]').val(start.format('MM/DD/YYYY') + '-' + end.format('MM/DD/YYYY'))
    });

    $('#created_at_daterange').on('cancel.daterangepicker', function(ev, picker) {
        $('#created_at_daterange span').html('');
        $('input[name="created_at_daterange"]').val('');
    });

    var createdAtDaterangeValue = $('input[name="created_at_daterange"]').val();
    if (createdAtDaterangeValue != '' && createdAtDaterangeValue != '-') {
        var dates = createdAtDaterangeValue.split('-'),
            createdAtStart = moment(dates[0].replace('/', '-')),
            createdAtEnd = moment(dates[1].replace('/', '-'));

        $('#created_at_daterange span').html(createdAtStart.format('MMMM D, YYYY') + ' - ' + createdAtEnd.format('MMMM D, YYYY'));
    }

    setTimeout(function() {
        window.location.reload();
    }, 3500 * 1000);
});
})(user_filter, sub_conf);
