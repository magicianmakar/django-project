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


    $('#download-normal-reviews').on('click', function(e) {
        e.preventDefault();
        window.ALIEXPRESS_REVIEWS = window.ALIEXPRESS_REVIEWS || [];
        var rows = getReviewRows(window.ALIEXPRESS_REVIEWS);
        var csv = createCSV(rows);
        startDownload(csv, 'reviews.csv');
    });

    $('#download-reviews-for-woocommerce').on('click', function(e) {
        e.preventDefault();
        window.ALIEXPRESS_REVIEWS = window.ALIEXPRESS_REVIEWS || [];
        var rows = getReviewRowsForWooCommerce(window.ALIEXPRESS_REVIEWS);
        var csv = createCSVForWooCommerce(rows);
        startDownload(csv, 'reviews-for-woocommerce.csv');
    });

    $('#send-reviews-to-store').on('click', function() {
        var btn = $(this);
        $.ajax({
            url: api_url('reviews-export', 'woo'),
            type: 'POST',
            data: {
                store: btn.data('store-id'),
                product: btn.data('product-id'),
                reviews: JSON.stringify(window.ALIEXPRESS_REVIEWS),
            },
            context: {
                btn: btn.bootstrapBtn('loading')
            },
            success: function(data) {
                var completeText = btn.data('reviews-sent-text');
                btn.html(completeText).addClass('disabled').prop('disabled', true);
            },
            error: function(data) {
                btn.bootstrapBtn('reset');
                displayAjaxError('Product Export', data);
            },
        });
    });

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
        if (!total) {
            total = 0;
        }
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

    function getReviewRows(reviews) {
        var rows = [];

        for (var i = 0, len = reviews.length; i < len; i++) {
            var review = reviews[i];
            var row = getReviewRow(review);
            rows.push(row);
        }

        return rows;
    }

    function getReviewRow(review) {
        return [
            "\"" + $('#product-title').data('handle') + "\"",
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

    function getReviewRowsForWooCommerce(reviews) {
        var rows = [];

        for (var i = 0, len = reviews.length; i < len; i++) {
            var review = reviews[i];
            var row = getReviewRowForWooCommerce(review);
            rows.push(row);
        }

        return rows;
    }

    function getReviewRowForWooCommerce(review) {
        return [
            '', // comment_ID
            $('#reviews_product_source_id').val(), // comment_post_ID
            review.author, // comment_author
            '', // comment_author_email
            '', // comment_author_url
            '', // comment_author_IP
            review.dateCreated, // comment_date
            review.dateCreated, // comment_date_gmt
            "\"" + review.body + "\"", // comment_content
            1, // comment_approved
            '', // comment_parent
            '', // user_id
            review.stars, // rating
            0, // verified
            '', // title
            '', // product_SKU
            review.title, // product_title
        ];
    }

    function createCSV(rows) {
        var csv = 'product_handle,state,rating,title,author,email,location,body,reply,created_at,replied_at\n';

        for (var i = 0, len = rows.length; i < len; i++) {
            var row = rows[i];
            csv += row.join();
            csv += '\n';
        }

        return csv;
    }

    function createCSVForWooCommerce(rows) {
        var csv =
            'comment_ID,comment_post_ID,comment_author,comment_author_email,' +
            'comment_author_url,comment_author_IP,comment_date,comment_date_gmt,' +
            'comment_content,comment_approved,comment_parent,user_id,rating,verified,' +
            'title,product_SKU,product_title\n';

        for (var i = 0, len = rows.length; i < len; i++) {
            var row = rows[i];
            csv += row.join();
            csv += '\n';
        }

        return csv;
    }

    function startDownload(reviews, filename) {
        var link;
        link = document.createElement('a');
        link.href = "data:text/csv;charset=utf-8,"  + encodeURI(reviews);
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }

    function getReviews(e) {
        e.preventDefault();
        window.extensionSendMessage({
            subject: 'getReviews',
            data: getPostData(),
        }, function(response) {
            if (response && response.ok) {
                window.ALIEXPRESS_REVIEWS = response.reviews;
                disableForm();
                $('#download-reviews').removeClass('disabled').prop('disabled', false);
                $('#send-reviews-to-store').removeClass('disabled').prop('disabled', false);
            } else {
                enableForm();
            }
        });
    }
})();
