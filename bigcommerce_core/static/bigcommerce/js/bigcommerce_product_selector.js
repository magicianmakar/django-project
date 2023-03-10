
function bigcommerceProductSearch (e) {
    var loadingContainer = $('#modal-bigcommerce-product .bigcommerce-find-loading');
    var productsContainer = $('#modal-bigcommerce-product .bigcommerce-products');

    var store = $('#modal-bigcommerce-product .bigcommerce-store').val();
    var query = $('#modal-bigcommerce-product .bigcommerce-find-product').val().trim();


    if (!$(this).prop('page')) {
        loadingContainer.show();
        productsContainer.empty();
    } else {
        $(this).bootstrapBtn('loading');
    }

    $.ajax({
        url: api_url('bigcommerce-products', 'bigcommerce'),
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
            var product_template = Handlebars.compile($("#bigcommerce-product-select-template").html());

            if (data.products.length === 0) {
                productsContainer.append($('<div class="text-center">' +
                    '<h3>No Product found with the given search query</h3>' +
                    '</div>'));
            }

            var store = this.store;
            $.each(data.products, function () {
                var el = $(product_template({product: this}));

                $('a.bigcommerce-product', el).click(function (e) {
                    e.preventDefault();

                    if (window.bigcommerceProductSelected) {
                        window.bigcommerceProductSelected(store, $(this).data('product-id'), {
                            title: $(this).data('product-title'),
                            image: $(this).data('product-image'),
                            shopified: $(this).data('shopified-id'),
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
                moreBtn.click(bigcommerceProductSearch);

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
    $('#modal-bigcommerce-product .bigcommerce-find-product').bindWithDelay('keyup', bigcommerceProductSearch, 500);
    $('#modal-bigcommerce-product .bigcommerce-store').on('change', bigcommerceProductSearch);
    $('#modal-bigcommerce-product').on('show.bs.modal', bigcommerceProductSearch);
});
