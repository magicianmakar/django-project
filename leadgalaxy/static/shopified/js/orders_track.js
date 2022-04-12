(function() {
    'use strict';

    $('.fulfill-btn').click(function(e) {
        $('#modal-fulfillment #fulfill-order-id').val($(this).attr('order-id'));
        $('#modal-fulfillment #fulfill-line-id').val($(this).attr('line-id'));
        $('#modal-fulfillment #fulfill-store').val($(this).attr('store'));
        $('#modal-fulfillment #fulfill-traking-number').val($(this).attr('tracking-number'));

        if ($(this).prop('fulfilled')) {
            return;
        }

        $('#modal-fulfillment').modal('show');
    });

    $('#fullfill-order-btn').click(function(e) {
        e.preventDefault();

        $(this).button('loading');
        var line_btn = $('.fulfill-btn[line-id="' + $('#modal-fulfillment #fulfill-line-id').val() + '"]');

        $.ajax({
            url: '/api/fulfill-order',
            type: 'POST',
            data: $('#modal-fulfillment form').serialize(),
            context: {
                btn: $(this),
                line: line_btn
            },
            success: function(data) {
                if (data.status == 'ok') {
                    $('#modal-fulfillment').modal('hide');
                    this.line.prop('fulfilled', true);
                    this.line.parents('tr').first().addClass('success');

                    swal.close();
                    toastr.success('Fulfillment Status changed to Fulfilled.', 'Fulfillment Status');
                } else {
                    displayAjaxError('Fulfill Order', data);
                }
            },
            error: function(data) {
                displayAjaxError('Fulfill Order', data);
            },
            complete: function() {
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

    function hideOrder(order_id, hide) {
        $.ajax({
            url: '/api/order-fullfill-hide',
            type: 'POST',
            data: {
                order: order_id,
                hide: hide
            },
            context: {
                order_id: order_id
            },
            success: function(data) {
                if (data.status == 'ok') {
                    $('tr[id="'+this.order_id+'"]').find('.hide-order, .show-order').hide();

                    if (hide) {
                        toastr.success('Order has been Archived.', 'Archive Order');
                    } else {
                        toastr.success('Order has been Un-Archived.', 'Un-Archive Order');
                    }
                } else {
                    displayAjaxError('Hide Order', data);
                }
            },
            error: function(data) {
                displayAjaxError('Hide Order', data);
            }
        });
    }

    $('.hide-order').click(function(e) {
        var order_id = $(this).attr('order-id');

        swal({
            title: 'Archive Order',
            text: 'Do you want to Archive this order?' +
                  '<br><b style="color:#dd5555">Archived orders ' +
                  'are not synced with Supplier</b>' +
                  '<br><b>Archive only Canceled or Completed Orders<b>',
            type: 'warning',
            html: true,
            animation: false,
            showCancelButton: true,
            confirmButtonColor: "#DD6B55",
            confirmButtonText: "Archive",
            cancelButtonText: "Cancel",
            closeOnCancel: true,
            closeOnConfirm: false,
            showLoaderOnConfirm: true,
        },
        function(isConfirmed) {
            if (isConfirmed) {
                hideOrder(order_id, true);
            }

            swal.close();
        });
    });

    $('.show-order').click(function(e) {
        hideOrder($(this).attr('order-id'), false);
    });

    $('.filter-btn').click(function(e) {
        Cookies.set('orders_filter', !$('#filter-form').hasClass('active'));

        $('#filter-form').toggleClass('active');
    });

    $('.delete-order-id-btn').click(function(e) {
        var tracks = $.map($('.order-track').filter(function(i, el) {
            return el.checked;
        }), function(el) {
            return {
                el: $(el).parents('tr'),
                order: $(el).attr('order-id'),
                line: $(el).attr('line-id'),
            };
        });

        if (!tracks.length) {
            return swal('Bulk Actions', 'Please select an order first', 'warning');
        }

        swal({
            title: 'Delete Order IDs',
            text: 'Do you want to delete the select Order IDs?',
            type: 'warning',
            html: true,
            animation: false,
            showCancelButton: true,
            confirmButtonColor: "#DD6B55",
            confirmButtonText: "Delete",
            cancelButtonText: "Cancel",
            closeOnCancel: true,
            closeOnConfirm: false,
            showLoaderOnConfirm: true,
        },
        function(isConfirmed) {
            if (!isConfirmed) {
                return;
            }

            P.map(tracks, function(track) {
                return $.ajax({
                    url: '/api/order-fulfill' + '?' + $.param({
                        'order_id': track.order,
                        'line_id': track.line,
                    }),
                    type: 'DELETE',
                }).done(function (data) {
                    $(track.el).fadeOut();
                });
            }, {
                concurrency: 2
            }).catch(function() {
            }).then(function() {
                swal.close();
            });
        });
    });

    $('.sync-selected-btn, .quick-sync-selected-btn').click(function(e) {
        var tracks = $.map($('.order-track').filter(function(i, el) {
            return el.checked;
        }), function(el) {
            return $(el).attr('track-id');
        });

        if (!tracks.length) {
            return swal('Bulk Actions', 'Please select an order first', 'warning');
        }

        window.syncOrderIds = tracks.join(',');

        $('#modal-tracking-update').modal({
            backdrop: 'static',
            keyboard: false
        });
        var target_id = e.target.id;
        if(target_id === "quick-sync-selected-orders")  {
            $('#quick-api-update').trigger('click');
        } else {
            $('.start-update-btn').trigger('click');
        }
    });

    $('.archive-selected-orders-btn').click(function(e) {
        var tracks = $.map($('.order-track').filter(function(i, el) {
            return el.checked;
        }), function(el) {
            return {
                el: $(el).parents('tr'),
                order: $(el).attr('order-id'),
                line: $(el).attr('line-id'),
            };
        });

        if (!tracks.length) {
            return swal('Bulk Actions', 'Please select an order first', 'warning');
        }

        swal({
            title: 'Archive Orders',
            text: 'Do you want to Archive the selected Order Tracks?',
            type: 'warning',
            html: true,
            animation: false,
            showCancelButton: true,
            confirmButtonColor: "#DD6B55",
            confirmButtonText: "Archive",
            cancelButtonText: "Cancel",
            closeOnCancel: true,
            closeOnConfirm: false,
            showLoaderOnConfirm: true,
        },
        function(isConfirmed) {
            if (!isConfirmed) {
                return;
            }

            P.map(tracks, function(track) {
                return $.ajax({
                    url: '/api/order-fullfill-hide',
                    type: 'POST',
                    data: {
                        order: $('.order-track', track.el).val(),
                        hide: true
                    }
                }).done(function (data) {
                    $(track.el).fadeOut();
                });
            }, {
                concurrency: 2
            }).catch(function() {
            }).then(function() {
                swal.close();
            });
        });
    });

    $('.check-all').on('ifChanged', function (e) {
        $('.order-track').iCheck(e.target.checked ? 'check' : 'uncheck');
    });

    $('[name="errors"]').chosen({
        search_contains: true,
        width: '100%'
    });

    $('[name="reason"]').chosen({
        search_contains: true,
        width: '100%'
    });

    $(".filter-form").submit(function() {
        $(this).find(":input").filter(function() {
            return ((this.name == 'tracking' && this.value === '') ||
                (this.name == 'reason' && this.value === '') ||
                (this.name == 'days_passed' && this.value === '') ||
                (this.name == 'hidden' && this.value == '0') ||
                (this.name == 'fulfillment' && this.value == '2') ||
                (this.name == 'query' && this.value.trim().length === 0));
        }).attr("disabled", "disabled");
        return true; // ensure form still submits
    });

    $('.export-tracked-orders').click(function(e) {
        var form_data = $('form.filter-form').serialize() +'&'+$.param({ 'store': $(this).data("store") });

        swal({
            title: 'Export Orders',
            text: 'Do you want to export the current page Order IDs and Tracking numbers?',
            animation: false,
            showCancelButton: true,
            confirmButtonText: "Export",
            cancelButtonText: "Cancel",
            closeOnCancel: true,
            closeOnConfirm: false,
            showLoaderOnConfirm: true,
        },
        function(isConfirmed) {
            if (!isConfirmed) {
                return;
            }

            $.ajax({
                url: '/api/export-tracked-orders',
                type: 'POST',
                data: form_data,
                success: function (data) {
                    swal({
                        text: 'Your request for Orders Export has been received. \nYour CSV file will be emailed to ' + data.email,
                        title: 'Export Orders',
                        type: 'success'
                    });
                },
                error: function (data) {
                    displayAjaxError('Export Orders', data);
                }
            });
        });
    });

    $(".track-details").click(function(e) {
        var btn = $(e.target);
        var detailsUrl = api_url('track-log') + '?' + $.param({
            'store': btn.attr('store'),
            'order_id': btn.attr('order-id'),
            'line_id': btn.attr('order-id'),
        });

        btn.button('loading');
        $('#modal-tracking-details .modal-content').load(detailsUrl, function(response, status) {
            btn.button('reset');
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

    if (Cookies.get('orders_filter') == 'true') {
        $('#filter-form').addClass('active');
    }
})();
