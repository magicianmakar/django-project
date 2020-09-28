$(function () {
    'use strict';


    var applyShowMore = function () {
        var numRowsToShow = 6;
        var moreText = 'Show more';
        var lessText = 'Show less';
        var moreLink = $('#more-salesfees').addClass('hidden');
        var rows = document.getElementById('salesfees-table-body').rows;

        if (rows.length > numRowsToShow) {
            var toggableRows = $(rows).slice(numRowsToShow).hide();
            moreLink.html(moreText).removeClass('hidden').on('click', function(e) {
                var newText = $(this).html() === moreText ? lessText: moreText;
                $(this).html(newText);
                toggableRows.toggle();
            });
        }
    };

    var getSalesfeesTable = function () {
        if (window.location.hash === '#salesfees') {
            $.get('/fulfilment-fee/fees-list', function (data) {
                $('#salesfees-table').html(data);
                applyShowMore();

            });
        }
    };

    $('a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
        getSalesfeesTable();
    });

    getSalesfeesTable();

});

