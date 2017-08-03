
function shopifyProductSearch (e) {
    var loadingContainer = $('#modal-shopify-product .shopify-find-loading');
    var productsContainer = $('#modal-shopify-product .shopify-products');

    var store = $('#modal-shopify-product .shopify-store').val();
    var query = $('#modal-shopify-product .shopify-find-product').val().trim();


    if (!$(this).prop('page')) {
        loadingContainer.show();
        productsContainer.empty();
    } else {
        if($.fn.hasOwnProperty('bootstrapBtn')) {
            $(this).bootstrapBtn('loading');
        } else {
            $(this).button('loading');
        }
    }

    $.ajax({
        url: '/api/shopify-products',
        type: 'POST',
        data: {
            store: store,
            query: query,
            page: $(this).prop('page'),
            connected: $('#modal-shopify-product').prop('connected'),
            hide_connected: $('#modal-shopify-product .hide-connected-product').prop('checked') ? 'true' : ''
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
                var el = $(product_template({
                    product: this,
                    connected_only: $('#modal-shopify-product').prop('connected')
                }));

                $('a.shopify-product', el).click(function (e) {
                    e.preventDefault();

                    if (window.shopifyProductSelected) {
                        window.shopifyProductSelected(store, $(this).data('product-id'), {
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
                moreBtn.click(shopifyProductSearch);

                productsContainer.append(moreBtn);
            }

            if($.fn.hasOwnProperty('bootstrapTooltip')) {
                $("[title]", productsContainer).bootstrapTooltip();
            } else {
                $("[title]", productsContainer).tooltip('loading');
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
    $('#modal-shopify-product .hide-connected-product').on('change', shopifyProductSearch);
    $('#modal-shopify-product').on('show.bs.modal', shopifyProductSearch);
});
