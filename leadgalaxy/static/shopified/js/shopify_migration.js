/* global $, toastr, swal, displayAjaxError */

(function(user_filter, sub_conf) {
'use strict';

$(function () {
    if (Cookies.get('shopify_products_filter') == 'true') {
        $('.filter-form').show();
    }
});

$('.filter-btn').click(function (e) {
    Cookies.set('shopify_products_filter', !$('.filter-form').is(':visible'));

    if (!$('.filter-form').is(':visible')) {
        $('.filter-form').fadeIn('fast');
    } else {
        $('.filter-form').fadeOut('fast');
    }
});

$('.save-filter-btn').click(function (e) {
    e.preventDefault();

    $.ajax({
        url: '/api/save-shopify-products-filter',
        type: 'POST',
        data: $('.filter-form').serialize(),
        success: function (data) {
            toastr.success('Products Filter', 'Saved');
            setTimeout(function() {
                $(".filter-form").trigger('submit');
            }, 1000);
        },
        error: function (data) {
            displayAjaxError('Products Filter', data);
        }
    });
});

$('.shopify-product-import-btn').click(function (e) {
    e.preventDefault();

    $('#modal-shopify-product .shopify-store').val($(this).attr('store')).trigger('change');
    $('#modal-shopify-product').modal('show');
});

$('.product-original-link').bindWithDelay('keyup', function (e) {
    var input = $(e.target);
    var parent = input.parents('.product-export-form');
    var product_url = input.val().trim();

    renderSupplierInfo(product_url, parent);
}, 200);

$('.add-supplier-info-btn').click(function (e) {
    e.preventDefault();
    var reload = $('#modal-supplier-link').prop('reload');

    $.ajax({
            url: '/api/import-product',
            type: 'POST',
            data: {
                store: $('#modal-supplier-link').prop('shopify-store'),
                supplier: $('.product-original-link').val(),
                vendor_name: $('.product-supplier-name').val(),
                vendor_url: $('.product-supplier-link').val(),
                product: $('#modal-supplier-link').prop('shopify-product'),
            },
        }).done(function (data) {
            toastr.success('Product is imported!', 'Product Import');

            $('#modal-supplier-link').modal('hide');

            if (reload) {
                window.location.reload();
            } else {
                setTimeout(function() {
                    window.location.href = '/product/' + data.product;
                }, 1500);
            }
        }).fail(function(data) {
            displayAjaxError('Product Import', data);
        }).always(function() {
        });
});

function disconnect(product_id) {
    swal({
        title: "Disconnect Product",
        text: "Are you sure you want to disconnect this product?",
        type: "warning",
        showCancelButton: true,
        closeOnCancel: true,
        closeOnConfirm: false,
        confirmButtonColor: "#DD6B55",
        confirmButtonText: "Disconnect",
        cancelButtonText: "Cancel"
    },
    function(isConfirmed) {
        if (isConfirmed) {
            $.ajax({
                url: '/api/product-connect?' + $.param({
                    product: product_id,
                }),
                type: 'DELETE',
                success: function (data) {
                    toastr.success('Shopify Migration', 'Product Successfully Disconnected!');
                },
                error: function (data) {
                    displayAjaxError('Connect Product', data);
                }
            });
        }
    });
}

function connect(store, shopify) {
    $('#modal-supplier-link').prop('shopify-store', store);
    $('#modal-supplier-link').prop('shopify-product', shopify);
    $('#modal-supplier-link').prop('reload', 'true');

    $('#modal-supplier-link').modal('show');
}

$('#apply-btn').click(function (e) {
    var action = $('#selected-actions').val();
    if (action == 'disconnect') {
        var product_ids = $("input[data-product][name=product]:checked").map(function(){
            return $(this).data('product');
        }).get();
        if (product_ids.length > 0) {
            swal({
                title: "Disconnect Products",
                text: "Are you sure you want to disconnect selected product(s)?",
                type: "warning",
                showCancelButton: true,
                closeOnCancel: true,
                closeOnConfirm: false,
                confirmButtonColor: "#DD6B55",
                confirmButtonText: "Disconnect",
                cancelButtonText: "Cancel"
            },
            function(isConfirmed) {
                if (isConfirmed) {
                    $.ajax({
                        url: '/api/product-connect?' + $.param({
                            product: product_ids.join(','), // comma-separated ids
                        }),
                        type: 'DELETE',
                        success: function (data) {
                            toastr.success('Shopify Migration', 'Product Successfully Connected!');
                        },
                        error: function (data) {
                            displayAjaxError('Connect Product', data);
                        }
                    });
                }
            });
        } else {
            swal('', "Please select connected products to disconnect.")
        }
    }
});

Vue.component('shopify-products-table', {
    template: '#shopify-products-table-tpl',
    props: ['task'],
    data: function () {
        return {
            task_id: null,
            products: [],
            prev: false,
            next: false,
            current: 1
        }
    },
    created: function () {
        this.pusherSub();
    },
    methods: {
        replacePageParam: function(value) {
            return replaceQueryParam('page', value);
        },
        pusherSub: function() {
            if (typeof(Pusher) === 'undefined') {
                toastr.error('This could be due to using Adblocker extensions<br>' +
                    'Please whitelist Shopified App website and reload the page<br>' +
                    'Contact us for further assistance',
                    'Pusher service is not loaded', {
                        timeOut: 0
                    });
                return;
            }

            var pusher = new Pusher(sub_conf.key);
            var channel = pusher.subscribe(sub_conf.channel);

            var vm = this;

            $.ajax({
                url: '/api/search-shopify-products',
                type: 'GET',
                data: user_filter,
                success: function(data) {
                    vm.task_id = data.task;

                    vm.products = [{'loading': true}];
                },
                error: function(data) {
                    displayAjaxError('Search Shopify Products', data);
                }
            });

            channel.bind('shopify-products-found', function(data) {
                if (vm.task_id && vm.task_id === data.task) {
                    console.log(data);
                    vm.prev = data.prev;
                    vm.current = data.current;
                    vm.next = data.next;
                    $.ajax({
                        url: '/api/search-shopify-products-cached',
                        type: 'GET',
                        data: {
                            task: vm.task_id
                        },
                        success: function(data) {
                            vm.products = data.products;
                            vm.$nextTick(function() {
                                $('.icheck').iCheck({
                                    checkboxClass: 'icheckbox_square-blue',
                                    radioClass: 'iradio_square-blue',
                                });

                                $('.product-connection-disconnect').click(function (e) {
                                    e.preventDefault();
                                    var product_id = $(this).data('product');
                                    disconnect(product_id);
                                });

                                $('.product-connection-connect').click(function (e) {
                                    e.preventDefault();
                                    connect(sub_conf.store, $(this).data('shopify'));
                                });
                            })
                        },
                        error: function(data) {
                            displayAjaxError('Search Shopify Products', data);
                        }
                    });
                }
            });
        },
    }
});

Vue.component('product-row', {
    template: '#product-row-tpl',
    props: ['product'],
});

// create the root instance
new Vue({
    el: '#products-wrapper'
});


})(user_filter, sub_conf);