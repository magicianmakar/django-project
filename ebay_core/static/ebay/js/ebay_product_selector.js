
function ebayProductSearch (e) {
    var loadingContainer = $('#modal-ebay-product .ebay-find-loading');
    var productsContainer = $('#modal-ebay-product .ebay-products');

    var store = $('#modal-ebay-product .ebay-store').val();
    var query = $('#modal-ebay-product .ebay-find-product').val().trim();


    if (!$(this).prop('page')) {
        loadingContainer.show();
        productsContainer.empty();
    } else {
        $(this).bootstrapBtn('loading');
    }

    $.ajax({
        url: api_url('ebay-products', 'ebay'),
        type: 'POST',
        data: {
            store: store,
            query: query,
            page: $(this).prop('page'),
            connected: true,
        },
        context: {
            store: store
        },
        success: function (data) {
            var product_template = Handlebars.compile($("#product-select-template").html());

            if (data.products.length === 0) {
                if (data.query) {
                    productsContainer.append($('<div class="text-center">' +
                        '<h3>No Product found with the given search query</h3>' +
                        '</div>'));
                } else {
                    productsContainer.append($('<div class="text-center">' +
                        '<h3>No products found. Please start a new import.</h3></br>' +
                        '<a href="/ebay/products/' + data.store + '/import" class="btn btn-success" id="start-new-import-button">' +
                        '<i class="fa fa-plus"></i> Start a New Import</button>' +
                        '</div>'));
                }
            }

            var store = this.store;
            $.each(data.products, function () {
                var el = $(product_template({product: this}));

                $('a.ebay-product', el).click(function (e) {
                    e.preventDefault();

                    if (window.ebayProductSelected) {
                        window.ebayProductSelected(store, $(this).data('product-id'), {
                            title: $(this).data('product-title'),
                            image: $(this).data('product-image'),
                            ebay: $(this).data('ebay-id'),
                            ebay_relist_id: $(this).data('ebay-relist-id'),
                        });
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
                moreBtn.click(ebayProductSearch);

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
    $('#modal-ebay-product .ebay-find-product').bindWithDelay('keyup', ebayProductSearch, 500);
    $('#modal-ebay-product .ebay-store').on('change', ebayProductSearch);
    $('#modal-ebay-product').on('show.bs.modal', ebayProductSearch);
});
