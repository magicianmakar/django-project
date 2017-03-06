
function shopifyProductSearch (e) {
    var loadingContainer = $('#modal-shopify-product .shopify-find-loading');
    var productsContainer = $('#modal-shopify-product .shopify-products');

    var store = $('#modal-shopify-product .shopify-store').val();
    var query = $('#modal-shopify-product .shopify-find-product').val().trim();


    if (!$(this).prop('page')) {
        loadingContainer.show();
        productsContainer.empty();
    } else {
        $(this).bootstrapBtn('loading');
    }

    $.ajax({
        url: '/api/shopify-products',
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
                productsContainer.append($('<div class="text-center"><h3>No Product found with the given search query</h3></div>'));
            }

            var store = this.store;
            $.each(data.products, function () {
                var el = $(product_template({product: this}));

                $('a.shopify-product', el).click(function () {
                    if (window.shopifyProductSelected) {
                        window.shopifyProductSelected(store, $(this).data('product-id'));
                    }
                });

                productsContainer.append(el);
            });

            productsContainer.find('.load-more-btn').remove();

            if (data.next) {
                var moreBtn = $('<button class="btn btn-outline btn-default btn-block ' +
                    'load-more-btn" data-loading-text="<i class=\'fa fa-circle-o-notch fa-spin\'>' +
                    '</i> Loading"><i class="fa fa-plus"></i> Load More</button>');

                moreBtn.prop('page', data.next);
                moreBtn.click(shopifyProductSearch);

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
    $('#modal-shopify-product .shopify-find-product').bindWithDelay('keyup', shopifyProductSearch, 500);
    $('#modal-shopify-product .shopify-store').on('change', shopifyProductSearch);
});
