
function multichannelProductSearch (e) {
    var loadingContainer = $('#modal-multichannel-product .multichannel-find-loading');
    var productsContainer = $('#modal-multichannel-product .multichannel-products');

    var query = $('#modal-multichannel-product .multichannel-find-product').val().trim();


    if (!$(this).prop('page')) {
        loadingContainer.show();
        productsContainer.empty();
    } else {
        $(this).bootstrapBtn('loading');
    }

    $.ajax({
        url: api_url('multichannel-products', 'multichannel'),
        type: 'POST',
        data: {
            query: query,
            page: $(this).prop('page'),
        },
        context: {},
        success: function (data) {
            var product_template = Handlebars.compile($("#multichannel-select-template").html());

            if (data.products.length === 0) {
                productsContainer.append($('<div class="text-center">' +
                    '<h3>No Product found with the given search query</h3>' +
                    '</div>'));
            }
            $.each(data.products, function () {
                var el = $(product_template({product: this}));

                $('a.multichannel-product', el).click(function (e) {
                    e.preventDefault();

                    if (window.multichannelProductSelected) {
                        window.multichannelProductSelected($(this).data('product-id'));
                    }
                });

                productsContainer.append(el);
            });

            productsContainer.find('.load-more-btn').remove();

            if (data.next) {
                var moreBtn = $('<button class="btn btn-outline btn-default btn-block ' +
                    'load-more-btn m-t-sm" data-loading-text="<i class=\'fa fa-circle-o-notch fa-spin\'>' +
                    '</i> Loading"><i class="fa fa-plus"></i> Load More</button>');

                moreBtn.prop('page', data.next);
                moreBtn.click(multichannelProductSearch);

                productsContainer.append(moreBtn);
            }
        },
        error: function (data) {
            productsContainer.append($('<div class="text-center"><h3>' +
                'Error occurred while searching for products</h3></div>'));
        },
        complete: function () {
            loadingContainer.hide();
        }
    });
}

$(function () {
    $('#modal-multichannel-product .multichannel-find-product').bindWithDelay('keyup', multichannelProductSearch, 500);
    $('#modal-multichannel-product').on('show.bs.modal', multichannelProductSearch);
});