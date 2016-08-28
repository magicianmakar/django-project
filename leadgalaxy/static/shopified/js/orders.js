/* global $, toastr, swal, displayAjaxError */

(function(user_filter) {
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
        if ((el.name  == 'desc' || el.name  == 'connected') && !$(el).prop('filtred'))  {
            el.value = JSON.stringify(el.checked);
            el.checked = true;
            $(el).prop('filtred', true);
        }

        var ret = (((!el.value || el.value.trim().length === 0) &&
                (el.type == 'text' || el.type.match(/select/) )) ||
            (el.name == 'sort' && el.value == user_filter.sort) ||
            (el.name == 'sort' && el.value == user_filter.sort) ||
            (el.name == 'desc' && el.value == user_filter.sort_type) ||
            (el.name == 'connected' && el.value == user_filter.connected) ||
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
        if ((el.name  == 'desc' || el.name  == 'connected') && !$(el).prop('filtred')) {
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
$('.placed-order-details').click(function (e) {
    e.preventDefault();

    var tr_parent = $(this).parents('tr').first();
    var order_id = $(this).attr('order-id');
    var source_id = $(this).attr('source-order-id');
    var line_id = $(this).attr('line-id');
    var html = '<ul>';
    html += '<li style="list-style:none">Aliexpress Order ID: <a target="_blank" '+
            'href="http://trade.aliexpress.com/order_detail.htm?orderId='+source_id+'">'+source_id+'</a></li>';
    html += '<li style="list-style:none">Order date: '+$(this).attr('order-date')+'</li>';
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
});

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
                        swal({
                            title: "Order ID",
                            text: "Product Order ID has been deleted.\nNote: The Order ID has not been removed from the order notes.",
                            type: "success"
                        });
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

$('.mark-as-ordered').click(function (e) {
    e.preventDefault();

    var orderData = {
        order_id: $(this).attr('order-id'),
        line_id: $(this).attr('line-id'),
        store: $(this).attr('store'),
        btn:  $(this)
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

        if (inputValue.match(/^[0-9]+$/) === null) {
            swal.showInputError("The entered Order ID is not valid.");
            return false;
        }

        $.ajax({
            url: '/api/order-fulfill',
            type: 'POST',
            data: {
                'store': orderData.store,
                'order_id': orderData.order_id,
                'line_id': orderData.line_id,
                'aliexpress_order_id': inputValue,
            },
            context: {orderData: orderData, aliexpress_id: inputValue},
            success: function (data) {
                if (data.status == 'ok') {
                    this.orderData.btn.text('#' + this.aliexpress_id);

                    var line = this.orderData.btn.parents('.line');
                    line.find('.line-ordered .badge').removeClass('badge-danger')
                                                     .addClass('badge-primary');

                    line.find('.line-ordered .ordered-status').text('Order Placed');
                    line.find('.line-tracking').text('Tracked');

                    findMarkedLines();

                    swal.close();
                    toastr.success('Item was marked as ordered in Shopified App.', 'Marked as Ordered');
                } else {
                    displayAjaxError('Mark as Ordered', data);
                }
            },
            error: function (data) {
                displayAjaxError('Mark as Ordered', data);
            },
            complete: function () {
            }
        });
    });
});

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

$('.place-order-btn').click(function (e) {
    var btn = $(this);
    var order_id = $(this).attr('order-id');
    var line_id = $(this).attr('line-id');

    var interval = setInterval(function() {
        var interval_id = placed_order_interval[order_id+'|'+line_id];
        if (interval_id.count >= 30) {
            clearInterval(interval_id.interval);
            return;
        }

        $.ajax({
            url: '/api/order-fulfill',
            type: 'GET',
            data: {
                order_id: order_id,
                line_id: line_id,
                count: interval_id.count
            },
            context: {
                btn: btn,
                order_id: order_id,
                line_id: line_id,
                interval_id: interval_id,
            },
            success: function (data) {
                if (data.length) {
                    this.btn.parents('.line').find('.line-order-id').text('Order ID: #'+data[0].source_id);
                    this.btn.parents('.line').find('.line-ordered .badge').removeClass('badge-danger').addClass('badge-primary');
                    this.btn.parents('.line').find('.line-ordered .ordered-status').text('Order Placed');
                    this.btn.parents('.line').find('.line-tracking').empty();

                    this.interval_id.count = 100;
                    clearInterval(this.interval_id.interval);
                }

                if  (this.interval_id.count >= 30) {
                    clearInterval(this.interval_id.interval);
                } else {
                    this.interval_id.count += 1;
                }
            },
            error: function (data) {
                clearInterval(this.interval_id.interval);
            },
            complete: function () {
                placed_order_interval[this.order_id+'|'+this.line_id] = this.interval_id;
            }
        });
    }, 10*1000);

    placed_order_interval[order_id + '|' + line_id] = {
        interval: interval,
        count: 1
    };
});

$('.auto-shipping-btn').click(function (e) {
    e.preventDefault();

    $('#shipping-modal').prop('data-href', $(this).attr('data-href'));
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

                var url = $('#shipping-modal').prop('data-href');

                url = url + $.param({
                    SAPlaceOrder: $('#shipping-modal').prop('data-order'),
                    SACompany: $(this).attr('company'),  // company
                    SACountry: $(this).attr('country')   // country_code
                });

                window.open(url, '_blank');
                $('#shipping-modal').modal('hide');

                $('#shipping-modal').prop('data-href', null);
                $('#shipping-modal').prop('data-order', null);
            })
            .css({cursor: 'pointer', height: '35px'})
            .find('td').css({'padding': '0 10px', 'vertical-align': 'middle'});
    });

});

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
    width: '325px'
});

$(function () {
    if (Cookies.get('orders_filter') == 'true') {
        $('.filter-form').show();
    }

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

    $('.note-panel').each(function (i, el) {
        $(el).css({
            height: $(el).parents('.shipping-info').outerHeight() + 'px',
            overflow: 'hidden'
        });
    });

    setTimeout(function() {
        window.location.reload();
    }, 3500 * 1000);
});
})(user_filter);
