
function GoogleProductSearch (e) {
    var loadingContainer = $('#modal-google-product .google-find-loading');
    var productsContainer = $('#modal-google-product .google-products');

    var store = $('#modal-google-product .google-store').val();
    var query = $('#modal-google-product .google-find-product').val().trim();


    if (!$(this).prop('page')) {
        loadingContainer.show();
        productsContainer.empty();
    } else {
        $(this).bootstrapBtn('loading');
    }

    $.ajax({
        url: api_url('google-products', 'google'),
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
                productsContainer.append($('<div class="text-center">' +
                    '<h3>No Product found with the given search query</h3>' +
                    '</div>'));
            }

            var store = this.store;
            $.each(data.products, function () {
                var el = $(product_template({product: this}));

                $('a.google-product', el).click(function (e) {
                    e.preventDefault();

                    if (window.GoogleProductSelected) {
                        window.GoogleProductSelected(store, $(this).data('product-id'), {
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
                moreBtn.click(GoogleProductSearch);

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
    $('#modal-google-product .google-find-product').bindWithDelay('keyup', GoogleProductSearch, 500);
    $('#modal-google-product .google-store').on('change', GoogleProductSearch);
    $('#modal-google-product').on('show.bs.modal', GoogleProductSearch);
});
