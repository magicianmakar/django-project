var checkRows = function() {
    var totalLinks = $('.order-export-row .collapse-info').length,
        totalLinksUp = $('.order-export-row .collapse-info i.fa-chevron-up').length;

    if (totalLinksUp < totalLinks) {
        $('.table thead tr .collapse-info i').addClass('fa-chevron-down').removeClass('fa-chevron-up');
    } else {
        $('.table thead tr .collapse-info i').addClass('fa-chevron-up').removeClass('fa-chevron-down');
    }
}

$('.order-export-row .collapse-info').on('click', function(e) {
    e.preventDefault();
    var counter = $(this).attr('data-counter'),
        tableRow = $('#info-'+counter),
        linkIcon = $(this).find('i');

    if (linkIcon.hasClass('fa-chevron-down')) {
        linkIcon.addClass('fa-chevron-up').removeClass('fa-chevron-down');
        tableRow.css('display', 'none');
    } else if (linkIcon.hasClass('fa-chevron-up')) {
        linkIcon.addClass('fa-chevron-down').removeClass('fa-chevron-up');
        tableRow.css('display', '');
    }
    checkRows();
});

$('.table thead tr .collapse-info').on('click', function() {
    e.preventDefault();
    var tableRows = $('.order-info-row'),
        infoLinkIcons = $('.order-export-row .collapse-info i'),
        linkIcon = $(this).find('i');

    if (linkIcon.hasClass('fa-chevron-down')) {
        linkIcon.addClass('fa-chevron-up').removeClass('fa-chevron-down');
        infoLinkIcons.addClass('fa-chevron-up').removeClass('fa-chevron-down');
        tableRows.css('display', 'none');
    } else if (linkIcon.hasClass('fa-chevron-up')) {
        linkIcon.addClass('fa-chevron-down').removeClass('fa-chevron-up');
        infoLinkIcons.addClass('fa-chevron-down').removeClass('fa-chevron-up');
        tableRows.css('display', '');
    }
});

$('.send-tracking-number').on('click', function() {
    var inputGroup = $(this).parents('.tracking-number'),
        input = inputGroup.find('[name="tracking_number"]'),
        fulfillmentInput = inputGroup.find('[name="fulfillment_id"]');
    $.ajax({
        url: $(this).attr('data-url'),
        type: 'POST',
        data: {
            tracking_number: input.val(),
            fulfillment_id: fulfillmentInput.val()
        },
        beforeSend: function() {
            inputGroup.next('.sk-spinner').removeClass('hide');
        },
        success: function(result) {
            if (result.success) {
               $(this).parents('.tracking-number').addClass('.has-success');
                inputGroup.next('.sk-spinner').addClass('hide');
            }
        }
    });
});