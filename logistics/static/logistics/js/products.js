$('.row-slide-parent').on('click', '.row-slide', function(e) {
    e.preventDefault();

    var arrowElem = $(this).find('.dropified-icons');
    var child = $(this).parents('.row-slide-parent').nextUntil('.row-slide-parent');
    if (arrowElem.hasClass('di-arrow-down')) {
        arrowElem.removeClass('di-arrow-down').addClass('di-arrow-up');
        child.removeClass('closed');
    } else {
        arrowElem.removeClass('di-arrow-up').addClass('di-arrow-down');
        child.addClass('closed');
    }
});

$('.connect-supplier').on('click', function(e) {
    e.preventDefault();

    $('#connect-product-modal').modal('show');
    $('#connect-product-modal .connect').data('supplier-id', $(this).data('supplier-id'));
});

$('.connect').on('click', function(e) {
    $('#connect-product-modal').modal('hide');

    var btn = $(this);
    var storeType = btn.data('store-type');
    var connectProduct = function (store, product_id, product_data) {
        console.log('hey');
        $.ajax({
            type: 'POST',
            url: api_url('connect', 'logistics'),
            data: {
                'store_type': storeType,
                'store_id': store,
                'product_id': product_id,
                'dropified_id': product_data.shopified,
                'id': btn.data('supplier-id'),
            },
            context: btn,
            success: function(data) {
                toastr.success('Product Connected.');
                swal.close();
                $('#modal-shopify-product:visible').modal('hide');
                $('#modal-commercehq-product:visible').modal('hide');
                $('#modal-woocommerce-product:visible').modal('hide');
                $('#modal-groovekart-product:visible').modal('hide');
                $('#modal-bigcommerce-product:visible').modal('hide');
                $('#modal-ebay-product:visible').modal('hide');
                $('#modal-fb-product:visible').modal('hide');
            },
            error: function(data) {
                displayAjaxError('Connect Product', data);
            }
        });
    };

    window.shopifyProductSelected = null;
    window.commercehqProductSelected = null;
    window.woocommerceProductSelected = null;
    window.groovekartProductSelected = null;
    window.bigcommerceProductSelected = null;
    window.ebayProductSelected = null;
    window.fbProductSelected = null;

    if (storeType === 'shopify') {
        $('#modal-shopify-product').modal('show');
        window.shopifyProductSelected = connectProduct;
    } else if (storeType == 'chq') {
        $('#modal-commercehq-product').modal('show');
        window.commercehqProductSelected = connectProduct;
    } else if (storeType == 'woo') {
        $('#modal-woocommerce-product').modal('show');
        window.woocommerceProductSelected = connectProduct;
    } else if (storeType == 'gkart') {
        $('#modal-groovekart-product').modal('show');
        window.groovekartProductSelected = connectProduct;
    } else if (storeType == 'bigcommerce') {
        $('#modal-bigcommerce-product').modal('show');
        window.bigcommerceProductSelected = connectProduct;
    } else if (storeType == 'ebay') {
        $('#modal-ebay-product').modal('show');
        window.ebayProductSelected = connectProduct;
    } else if (storeType == 'fb') {
        $('#modal-fb-product').modal('show');
        window.fbProductSelected = connectProduct;
    }
});

$('.delete-product').on('click', function (e) {
    e.preventDefault();

    var btn = $(this);
    swal({
        title: 'Delete Product',
        text: 'Are you sure you want to delete this Product?',
        type: "warning",
        showCancelButton: true,
        animation: false,
        cancelButtonText: "Cancel",
        confirmButtonText: 'Yes',
        confirmButtonColor: "#DD6B55",
        closeOnCancel: true,
        closeOnConfirm: false,
        showLoaderOnConfirm: true,
    },
    function(isConfirm) {
        if (isConfirm) {

            $.ajax({
                type: 'DELETE',
                url: api_url('product', 'logistics'),
                data: {'id': btn.data('id')},
                context: btn,
                success: function(data) {
                    toastr.success('Product Deleted.');
                    swal.close();
                    btn.parents('tr').remove();
                },
                error: function(data) {
                    displayAjaxError('Delete Product', data);
                }
            });
        }
    });
});

$('.delete-supplier').on('click', function (e) {
    e.preventDefault();

    var btn = $(this);
    swal({
        title: 'Delete Product',
        text: 'Are you sure you want to delete this Product?',
        type: "warning",
        showCancelButton: true,
        animation: false,
        cancelButtonText: "Cancel",
        confirmButtonText: 'Yes',
        confirmButtonColor: "#DD6B55",
        closeOnCancel: true,
        closeOnConfirm: false,
        showLoaderOnConfirm: true,
    },
    function(isConfirm) {
        if (isConfirm) {

            $.ajax({
                type: 'DELETE',
                url: api_url('supplier', 'logistics'),
                data: {'id': btn.data('id')},
                context: btn,
                success: function(data) {
                    toastr.success('Product Deleted.');
                    swal.close();
                    btn.parents('tr').remove();
                },
                error: function(data) {
                    displayAjaxError('Delete Product', data);
                }
            });
        }
    });
});
