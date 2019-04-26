(function() {
    'use strict';

    var $isExtensionReady = isExtensionReady();

    $('a[data-toggle="tab"]').on('shown.bs.tab', function(e) {
        var target = $(e.target).data("auto-click");
        if (target == '#reviews') {
            $isExtensionReady.done(updateReviewsForm);
        }
    });

    if (window.location.hash) {
        if (window.location.hash.substring(1) === 'reviews') {
            $isExtensionReady.done(updateReviewsForm);
        }
    }

    $('#review-form').submit(getReviews)
                     .find('input, select')
                     .not('#reviews_pages')
                     .not('#reviews_sort')
                     .not('#only_text_reviews')
                     .on('change', updateReviewsForm);

    function updateReviewsForm() {
        disableForm();
        window.extensionSendMessage({
            subject: 'getFeedbackPageDetails',
            data: getPostData(),
        }, function(response) {
            enableForm();

            if (response && response.ok) {
                addDetails(response.details);
            }
        });
    }

    function getPostData() {
        return {
            product_url: $('#reviews_product_url').val(),
            reviews_star: $('#reviews_star').val(),
            reviews_sort: $('#reviews_sort').val(),
            reviews_with_images: $('#reviews_with_images').prop('checked'),
            reviews_personal_info: $('#reviews_personal_info').prop('checked'),
            reviews_my_country: $('#reviews_my_country').prop('checked'),
            only_text_reviews: $('#only_text_reviews').prop('checked'),
            reviews_pages: $('#reviews_pages').val(),
        };
    }

    function labelTotal(total) {
        return total + ' ' + (total === 1 ? 'page' : 'pages');
    }

    function addDetails(data) {
        $('label[for=reviews_pages]').text('Pages to import (Total: ' + labelTotal(data.review_pages) + '): ');
        $('#reviews_pages').attr('max', data.review_pages);
        $('label[for=reviews_with_images]').text('With pictures (' + labelTotal(data.with_pictures) + ')');
        $('label[for=reviews_personal_info]').text('With personal information (' + labelTotal(data.with_personal_info) + ')');
    }

    function enableForm() {
        $('#review-form').find('input, select, button').prop('disabled', false);
    }

    function disableForm() {
        $('#review-form').find('input, select, button').prop('disabled', true);
    }

    function addDownloadButton(rows) {
        var csv = 'product_handle,state,rating,title,author,email,location,body,reply,created_at,replied_at\n';

        for (var i = 0, len = rows.length; i < len; i++) {
            var row = rows[i];
            csv += row.join();
            csv += '\n';
        }

        $("<span>&nbsp;<a href=\"data:text/csv;charset=utf-8," +
            encodeURI(csv) + "\" class='btn btn-info " +
            "csv-reviews' id='csv_reviews')' target='_blank' download='reviews.csv'" +
            "><i class='fa fa-download'></i> Download</a></span>"
         ).insertAfter('#import-reviews-btn');
    }

    function getReviewRow(review) {
        return [
            $('#product-title').data('handle'),
            'published',
            review.stars,
            review.title,
            review.author,
            'user@example.mail',
            review.location,
            "\"" + review.body + "\"",
            "\"\"",
            review.dateCreated,
            "\"\"",
        ];
    }

    function getReviewRows(reviews) {
        var rows = [];

        for (var i = 0, len = reviews.length; i < len; i++) {
            var review = reviews[i];
            var row = getReviewRow(review);
            rows.push(row);
        }

        return rows;
    }

    function getReviews(e) {
        e.preventDefault();
        window.extensionSendMessage({
            subject: 'getReviews',
            data: getPostData(),
        }, function(response) {
            if (response && response.ok) {
                var rows = getReviewRows(response.reviews);
                addDownloadButton(rows);
                disableForm();
            } else {
                enableForm();
            }
        });
    }
})();
