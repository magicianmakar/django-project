
function commercehqProductSearch (e) {
    var loadingContainer = $('#modal-commercehq-product .commercehq-find-loading');
    var productsContainer = $('#modal-commercehq-product .commercehq-products');

    var store = $('#modal-commercehq-product .commercehq-store').val();
    var query = $('#modal-commercehq-product .commercehq-find-product').val().trim();


    if (!$(this).prop('page')) {
        loadingContainer.show();
        productsContainer.empty();
    } else {
        $(this).bootstrapBtn('loading');
    }

    $.ajax({
        url: api_url('commercehq-products', 'chq'),
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

                $('a.commercehq-product', el).click(function (e) {
                    e.preventDefault();

                    if (window.commercehqProductSelected) {
                        window.commercehqProductSelected(store, $(this).data('product-id'));
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
                moreBtn.click(commercehqProductSearch);

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

$('#modal-commercehq-product .commercehq-find-product').bindWithDelay('keyup', commercehqProductSearch, 500);
$('#modal-commercehq-product .commercehq-store').on('change', commercehqProductSearch);
$('#modal-commercehq-product .commercehq-find-product').trigger('keyup');
