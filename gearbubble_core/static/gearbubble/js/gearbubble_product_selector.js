
function gearbubbleProductSearch (e) {
    var loadingContainer = $('#modal-gearbubble-product .gearbubble-find-loading');
    var productsContainer = $('#modal-gearbubble-product .gearbubble-products');

    var store = $('#modal-gearbubble-product .gearbubble-store').val();
    var query = $('#modal-gearbubble-product .gearbubble-find-product').val().trim();


    if (!$(this).prop('page')) {
        loadingContainer.show();
        productsContainer.empty();
    } else {
        $(this).bootstrapBtn('loading');
    }

    $.ajax({
        url: api_url('gearbubble-products', 'gear'),
        type: 'POST',
        data: {
            store: store,
            query: query,
            page: $(this).prop('page')
        },
        context: {
            store: store
        },
        success: function (data) {
            var product_template = Handlebars.compile($("#product-select-template").html());

            if (data.products.length === 0) {
                productsContainer.append($('<div class="text-center">' +
                    '<h3>No more products found for the given search query</h3>' +
                    '</div>'));
            }

            var store = this.store;
            $.each(data.products, function () {
                var el = $(product_template({product: this}));

                $('a.gearbubble-product', el).click(function (e) {
                    e.preventDefault();

                    if (window.gearbubbleProductSelected) {
                        window.gearbubbleProductSelected(store, $(this).data('product-id'));
                    }
                });

                productsContainer.append(el);
            });

            productsContainer.find('.load-more-btn').remove();

            if (data.next && data.products.length > 0) {
                var moreBtn = $('<button class="btn btn-outline btn-default btn-block ' +
                    'load-more-btn" data-loading-text="<i class=\'fa fa-circle-o-notch fa-spin\'>' +
                    '</i> Loading"><i class="fa fa-plus"></i> Load More</button>');

                moreBtn.prop('page', data.next);
                moreBtn.click(gearbubbleProductSearch);

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
    $('#modal-gearbubble-product .gearbubble-find-product').bindWithDelay('keyup', gearbubbleProductSearch, 500);
    $('#modal-gearbubble-product .gearbubble-store').on('change', gearbubbleProductSearch);
    $('#modal-gearbubble-product').on('show.bs.modal', gearbubbleProductSearch);
});
