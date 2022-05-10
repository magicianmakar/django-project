/* global $, toastr, swal, displayAjaxError */

(function(user_filter, sub_conf) {
'use strict';

$('.product-original-link').bindWithDelay('keyup', function (e) {
    var input = $(e.target);
    var parent = input.parents('.product-export-form');
    var product_url = input.val().trim();

    renderSupplierInfo(product_url, parent);
}, 200);

function verifyPusherIsDefined() {
    if (typeof(Pusher) === 'undefined') {
        toastr.error('This could be due to using Adblocker extensions<br>' +
            'Please whitelist Dropified website and reload the page<br>' +
            'Contact us for further assistance',
            'Pusher service is not loaded', {timeOut: 0});
        return false;
    }
    return true;
}

function addConnectEventListener() {
    $('.product-connection-connect').on('click', function (e) {
        e.preventDefault();
        connect(
            sub_conf.store,
            $(this).data('product'),
            $(this).data('variants-count'),
            $(this).data('csv-index-position')
        );
    });
}

function connect(store, ebayProduct, variantsCount, csvIndexPosition) {
    var modal = $('#modal-supplier-link');
    modal.prop('ebay-store', store);
    modal.prop('ebay-product', ebayProduct);
    modal.prop('ebay-product-variants-count', variantsCount);
    modal.prop('ebay-csv-index-position', csvIndexPosition);
    modal.prop('reload', 'true');

    modal.modal('show');
}

Vue.component('ebay-imported-products-table', {
    template: '#ebay-imported-products-table-tpl',
    props: ['task'],
    data: function () {
        return {
            task_id: null,
            products: [{'loading': true}],
            prev: false,
            next: false,
            current: 1
        };
    },
    methods: {
        replacePageParam: function(value) {
            return replaceQueryParam('page', value);
        },
        addDisconnectEventListener: function() {
            var vm = this;
            $('.product-connection-disconnect').on('click', function (e) {
                e.preventDefault();
                var product_id = $(this).data('product');
                vm.disconnect(sub_conf.store, product_id);
            });
        },
        addSyncEventListener: function() {
            var vm = this;
            $('.product-connection-sync').on('click', function (e) {
                e.preventDefault();
                vm.sync(
                    sub_conf.store,
                    $(this).data('product'),
                    $(this).data('variants-count'),
                    $(this).data('csv-index-position')
                );
            });
        },
        addConnectSupplierButtonListener: function() {
            var vm = this;

            $('.add-supplier-info-btn').click(function (e) {
                e.preventDefault();
                if (!verifyPusherIsDefined()) {
                    return;
                }

                var pusher = new Pusher(sub_conf.key);
                var channel = pusher.subscribe(sub_conf.channel);

                var modal = $('#modal-supplier-link');
                var btn = $('.add-supplier-info-btn');
                btn.bootstrapBtn('loading');
                btn.addClass('disabled');
                var task_id;
                var product_id = modal.prop('ebay-product');
                var vendor_name = $('.product-supplier-name').val();
                var supplier_url = $('.product-original-link').val();

                channel.bind('ebay-product-import-completed', function(eventData) {
                    if (eventData.task === task_id) {
                        pusher.unsubscribe(channel);

                        if (eventData.success) {
                            var index = vm.products.findIndex(function(element) {
                                return element.id === product_id;
                            });
                            toastr.success('Product ' + vm.products[index].title + ' has been imported!',
                                'Product Import');
                            btn.bootstrapBtn('reset');
                            btn.removeClass('disabled');
                            modal.modal('hide');

                            vm.products[index].status = 'connected';
                            vm.products[index].product_link = eventData.product_link;
                            vm.products[index].supplier_name = vendor_name;
                            vm.products[index].original_url = supplier_url;
                            vm.$nextTick(function() {
                                vm.addSyncEventListener();
                                vm.addDisconnectEventListener();
                            });
                        } else {
                            btn.bootstrapBtn('reset');
                            btn.removeClass('disabled');
                            displayAjaxError('Product Import', eventData);
                        }
                    }
                });

                channel.bind('pusher:subscription_succeeded', function() {
                     $.ajax({
                        url: api_url('import-product', 'ebay'),
                        type: 'POST',
                        data: {
                            store: modal.prop('ebay-store'),
                            supplier: supplier_url,
                            vendor_name: vendor_name,
                            vendor_url: $('.product-supplier-link').val(),
                            product: product_id,
                            variants_count: modal.prop('ebay-product-variants-count'),
                            csv_index_position: modal.prop('ebay-csv-index-position'),
                        },
                    }).done(function (data) {
                        task_id = data.task;
                    }).fail(function(data) {
                        btn.bootstrapBtn('reset');
                        btn.removeClass('disabled');
                        displayAjaxError('Product Import', data);
                    });
                });
            });
        },
        disconnect: function(store_id, product_id) {
            var vm = this;

            swal({
                title: 'Disconnect Product',
                text: 'Are you sure you want to disconnect this product?',
                type: 'warning',
                showCancelButton: true,
                closeOnCancel: true,
                closeOnConfirm: true,
                confirmButtonColor: "#DD6B55",
                confirmButtonText: 'Disconnect',
                cancelButtonText: 'Cancel'
            },
            function(isConfirmed) {

                if (isConfirmed) {
                    if (!verifyPusherIsDefined()) {
                        return;
                    }
                    var product_row = $('[data-product="' + product_id + '"]').closest('tr');
                    var btn = $('.product-connection-disconnect', product_row);
                    btn.bootstrapBtn('loading');
                    btn.addClass('disabled');
                    var pusher = new Pusher(sub_conf.key);
                    var channel = pusher.subscribe(sub_conf.channel);

                    channel.bind('product-delete', function(eventData) {
                        if (eventData.product === product_id) {
                            pusher.unsubscribe(channel);
                            btn.bootstrapBtn('reset');
                            btn.removeClass('disabled');

                            if (eventData.success) {
                                swal.close();
                                var index = vm.products.findIndex(function(element) {
                                    return element.id === product_id;
                                });
                                toastr.success('The product ' + vm.products[index].title + ' has been disconnected.',
                                    'Disconnected!');
                                vm.products[index].status = 'non-connected';
                                vm.products[index].product_link = null;
                                vm.products[index].supplier_name = '';
                                vm.products[index].original_url = '';
                                vm.$nextTick(function() {
                                    addConnectEventListener();
                                });
                            }
                            if (eventData.error) {
                                displayAjaxError('Disconnect Product', eventData);
                            }
                        }
                    });

                    channel.bind('pusher:subscription_succeeded', function() {
                        $.ajax({
                            url: api_url('disconnect-product', 'ebay'),
                            data: {
                                product: product_id,
                                store: store_id,
                            },
                            type: 'DELETE',
                            success: function(data) {},
                            error: function(data) {
                                pusher.unsubscribe(channel);
                                displayAjaxError('Disconnect Product', data);
                            }
                        });
                    });
                }
            });
        },
        sync: function(store_id, product_id, variants_count, csv_index) {
            var vm = this;

            if (!verifyPusherIsDefined()) {
                return;
            }
            var product_row = $('[data-product="' + product_id + '"]').closest('tr');
            var btn = $('.product-connection-sync', product_row);
            btn.bootstrapBtn('loading');
            btn.addClass('disabled');
            var pusher = new Pusher(sub_conf.key);
            var channel = pusher.subscribe(sub_conf.channel);

            channel.bind('ebay-product-sync-completed', function(eventData) {
                if (eventData.product === product_id) {
                    pusher.unsubscribe(channel);
                    btn.bootstrapBtn('reset');
                    btn.removeClass('disabled');

                    if (eventData.success) {
                        var index = vm.products.findIndex(function(element) {
                            return element.id === product_id;
                        });
                        toastr.success('The product ' + vm.products[index].title + ' has been synced.', 'Synced!');
                    } else {
                        displayAjaxError('Sync Product', eventData.error);
                    }
                }
            });

            channel.bind('pusher:subscription_succeeded', function() {
                $.ajax({
                    url: api_url('update-product-with-import', 'ebay'),
                    data: {
                        product: product_id,
                        variants_count: variants_count,
                        csv_index_position: csv_index,
                    },
                    type: 'POST',
                    success: function(data) {},
                    error: function(data) {
                        btn.bootstrapBtn('reset');
                        btn.removeClass('disabled');
                        pusher.unsubscribe(channel);
                        displayAjaxError('Sync Product', data);
                    }
                });
            });
        },
        pusherSub: function() {
            var vm = this;
            vm.products = [{'loading': true}];

            $.ajax({
                url: api_url('import-product-options', 'ebay'),
                type: 'GET',
                data: user_filter,
                success: function(data) {
                    vm.task_id = data.task;
                    vm.products = [{'loading': true}];
                },
                error: function(data) {
                    displayAjaxError('eBay Import Products', data);
                }
            });

            window.channel.bind('ebay-import-products-found', function(data) {
                if (vm.task_id && vm.task_id === data.task) {
                    vm.prev = data.prev;
                    vm.current = data.current;
                    vm.next = data.next;
                    vm.products = data.products;
                    vm.$nextTick(function() {
                        vm.addDisconnectEventListener();
                        vm.addSyncEventListener();
                        addConnectEventListener();
                        vm.addConnectSupplierButtonListener();
                    });
                    if (data.errors && data.errors.length) {
                        displayAjaxError('eBay Import Products', data);
                    }
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
var vue = new Vue({
    el: '#ebay-products-wrapper'
});

if (typeof(Pusher) !== 'undefined') {
    // Pusher.logToConsole = true;
    window.pusher = new Pusher(sub_conf.key);
    window.channel = window.pusher.subscribe(sub_conf.channel);
    window.channel.bind('pusher:subscription_succeeded', function(data){
        vue.$refs.ebayImportedProductsTable.pusherSub();
    });
} else {
    toastr.error('This could be due to using Adblocker extensions<br>' +
        'Please whitelist Shopified App website and reload the page<br>' +
        'Contact us for further assistance',
        'Pusher service is not loaded', {
            timeOut: 0
        });
}

})(user_filter, sub_conf);
