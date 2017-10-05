
function woocommerceProductSearch (e) {
    var loadingContainer = $('#modal-woocommerce-product .woocommerce-find-loading');
    var productsContainer = $('#modal-woocommerce-product .woocommerce-products');

    var store = $('#modal-woocommerce-product .woocommerce-store').val();
    var query = $('#modal-woocommerce-product .woocommerce-find-product').val().trim();


    if (!$(this).prop('page')) {
        loadingContainer.show();
        productsContainer.empty();
    } else {
        $(this).bootstrapBtn('loading');
    }

    $.ajax({
        url: api_url('woocommerce-products', 'woo'),
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
                    '<h3>No Product found with the given search query</h3>' +
                    '</div>'));
            }

            var store = this.store;
            $.each(data.products, function () {
                var el = $(product_template({product: this}));

                $('a.woocommerce-product', el).click(function (e) {
                    e.preventDefault();

                    if (window.woocommerceProductSelected) {
                        window.woocommerceProductSelected(store, $(this).data('product-id'));
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
                moreBtn.click(woocommerceProductSearch);

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
    $('#modal-woocommerce-product .woocommerce-find-product').bindWithDelay('keyup', woocommerceProductSearch, 500);
    $('#modal-woocommerce-product .woocommerce-store').on('change', woocommerceProductSearch);
    $('#modal-woocommerce-product').on('show.bs.modal', woocommerceProductSearch);
});
