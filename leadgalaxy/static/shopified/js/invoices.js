$(function () {
    'use strict';

    var applyPayInvoiceAction = function () {
       $('.pay-invoice-link').on('click', function(e) {
            e.preventDefault();
            var invoicePayUrl = $(e.target).data('invoice-pay-url');
            $('#pay-now-modal').modal('show');
            $('#pay-now-modal .pay-invoice').removeAttr('disabled');
            $('#pay-now-modal .pay-invoice').data('invoice-pay-url', invoicePayUrl);
        });
    };

    var applyShowMore = function () {
        var numRowsToShow = 6;
        var moreText = 'Show more';
        var lessText = 'Show less';
        var moreLink = $('#more-invoices').addClass('hidden');
        var rows = document.getElementById('invoice-table-body').rows;

        if (rows.length > numRowsToShow) {
            var toggableRows = $(rows).slice(numRowsToShow).hide();
            moreLink.html(moreText).removeClass('hidden').on('click', function(e) {
                var newText = $(this).html() === moreText ? lessText: moreText;
                $(this).html(newText);
                toggableRows.toggle();
            });
        }
    };

    var applyModalActions = function () {
        $('#pay-now-modal .pay-invoice').click(function () {
            $(this).button('loading');
            var invoicePayUrl = $(this).data('invoice-pay-url');
            $.ajax({
                url: invoicePayUrl,
                type: 'POST',
                data: {},
                success: function(data) {
                    toastr.success('Invoice paid.', 'Thank you');
                    getInvoicesTable();
                },
                error: function(data) {
                    displayAjaxError('Invoice payment error', data);
                }
            }).always(
                function() {
                    $(this).button('reset');
                    $('#pay-now-modal').modal('hide');
                }.bind(this)
            );
        });
    };

    var getInvoicesTable = function () {
        if (window.location.hash === '#invoices') {
            $.get('/user/profile/invoices', function (data) {
                $('#invoice-table').html(data);
                applyShowMore();
                applyPayInvoiceAction();
            })
        }
    };

    $('a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
        getInvoicesTable();
    });

    getInvoicesTable();
    applyModalActions();
});

