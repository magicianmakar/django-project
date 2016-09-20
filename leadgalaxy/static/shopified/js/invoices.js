$(function () {
    'use strict';

    var applyPayInvoiceAction = function () {
       $('.pay-invoice-link').on('click', function(e) {
            e.preventDefault();
            var invoiceId = $(this).data('invoice-id');
            $('#pay-invoice-form-' + invoiceId).submit();
        });
    }

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
});

