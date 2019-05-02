
function groovekartProductSearch (e) {
    var loadingContainer = $('#modal-groovekart-product .groovekart-find-loading');
    var productsContainer = $('#modal-groovekart-product .groovekart-products');

    var store = $('#modal-groovekart-product .groovekart-store').val();
    var query = $('#modal-groovekart-product .groovekart-find-product').val().trim();


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
        url: api_url('groovekart-products', 'gkart'),
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

                $('a.groovekart-product', el).click(function (e) {
                    e.preventDefault();

                    if (window.groovekartProductSelected) {
                        window.groovekartProductSelected(store, $(this).data('product-id'));
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
                moreBtn.click(groovekartProductSearch);

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
    $('#modal-groovekart-product .groovekart-find-product').bindWithDelay('keyup', groovekartProductSearch, 500);
    $('#modal-groovekart-product .groovekart-store').on('change', groovekartProductSearch);
    $('#modal-groovekart-product').on('show.bs.modal', groovekartProductSearch);
});
