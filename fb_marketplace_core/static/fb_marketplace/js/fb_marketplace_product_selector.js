
function fb_marketplaceProductSearch (e) {
    var loadingContainer = $('#modal-fb_marketplace-product .fb_marketplace-find-loading');
    var productsContainer = $('#modal-fb_marketplace-product .fb_marketplace-products');

    var store = $('#modal-fb_marketplace-product .fb_marketplace-store').val();
    var query = $('#modal-fb_marketplace-product .fb_marketplace-find-product').val().trim();


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
}
$(function () {
    $('#modal-fb_marketplace-product .fb_marketplace-find-product').bindWithDelay('keyup', fb_marketplaceProductSearch, 500);
    $('#modal-fb_marketplace-product .fb_marketplace-store').on('change', fb_marketplaceProductSearch);
    $('#modal-fb_marketplace-product').on('show.bs.modal', fb_marketplaceProductSearch);
});
