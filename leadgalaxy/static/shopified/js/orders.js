//'use strict';
/* global $, toastr, swal, displayAjaxError */

var image_cache = {};

$(function () {
    $(".itooltip").tooltip();
});

function loadVriantImages(target) {
    if (typeof(terget) === 'undefined') {
        target = $('.lazyload');
    } else {
        target = $('.lazyload', target);
    }

    target.each(function (i, el) {
        if (!$(el).prop('image-loaded')) {
            var cache_name = $(el).attr('store')+'|'+$(el).attr('product')+'|'+$(el).attr('variant');

            if (cache_name in image_cache) {
                $(el).attr('src', image_cache[cache_name]);
                return;
            }

            $.ajax({
                url: '/api/product-variant-image',
                type: 'GET',
                data: {
                    store: $(el).attr('store'),
                    product: $(el).attr('product'),
                    variant: $(el).attr('variant'),
                },
                context: {img: $(el), cache_name: cache_name},
                success: function (data) {
                    if (data.status == 'ok') {
                        this.img.attr('src', data.image);

                        image_cache[cache_name] = data.image;
                    }
                },
                error: function (data) {
                },
                complete: function () {
                    this.img.prop('image-loaded', true);
                }
            });
        }
    });
}

$(".more-info").click(function (e) {
    e.preventDefault();

    var element = $(this).find('i');
    var target = $(this).parents('tr').next();

    loadVriantImages(target);

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
    $('#modal-fulfillment #fulfill-quantity').val($(this).attr('quantity'));
    $('#modal-fulfillment #fulfill-order-id').val($(this).attr('order-id'));
    $('#modal-fulfillment #fulfill-line-id').val($(this).attr('line-id'));
    $('#modal-fulfillment #fulfill-store').val($(this).attr('store'));

    if ($(this).prop('fulfilled')) {
        return;
    }

    $('#modal-fulfillment').modal('show');
});

$('#fullfill-order-btn').click(function (e) {
    e.preventDefault();

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
                swal('Fulfillment Status', 'Fulfillment Status changed to Fulfilled', 'success');
                this.line.prop('fulfilled', true);
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
    $('.filter-form').toggle('fade');
});

$(".filter-form").submit(function() {
    $(this).find(":input").filter(function(){
        return ((this.name == 'sort' && this.value == 'desc') ||
            (this.name == 'status' && this.value == 'open') ||
            (this.name == 'fulfillment' && this.value == 'unshipped') ||
            (this.name == 'financial' && this.value == 'any') ||
            (this.name == 'query' && this.value.trim().length === 0));
    }).attr("disabled", "disabled");
    return true; // ensure form still submits
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
    var data = JSON.parse(JSON.parse(atob($(this).attr('data'))));
    var html = '<ul>';
    html += '<li style="list-style:none">Aliexpress Order ID: <a target="_blank" href="http://trade.aliexpress.com/order_detail.htm?orderId='+source_id+'">'+source_id+'</a></li>';
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
                'aliexpress_order_trade': ''
            },
            context: {orderData: orderData},
            success: function (data) {
                if (data.status == 'ok') {
                    this.orderData.btn.parents('tr').first().addClass('success');
                    findMarkedLines();
                    swal('Marked as Ordered.', 'Item was marked as ordered in Shopified App', 'success');
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
                    swal('Add Note', 'Note added to the order in Shopify.', 'success');
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
function findMarkedLines() {
    $('.fulfillment-status button.status-orderd-btn').remove();

    $('.var-info table tr[class="success"]').each(function (i, tr) {
        var orderTR = $(tr).parents('tr').prev();
        orderTR.find('.fulfillment-status').append(
            $('<button class="btn btn-info btn-circle btn-xs itooltip no-outline status-orderd-btn" type="button" title="Order with lines marked as Ordered"><i class="fa fa-check"></i></button>').click(function (e) {
                $(this).parents('tr').find('.more-info').trigger('click');
            })
        );
    });

    $(".itooltip").tooltip();
}

$(function () {
    $('.help-select').each(function (i, el) {
        $('option', el).each(function (index, option) {
            $(option).attr('title', $(option).text());
            $(option).text(toTitleCase($(option).val()));
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

    findMarkedLines();
    loadVriantImages('.orders .line');
});
