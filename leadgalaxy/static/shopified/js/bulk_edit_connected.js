(function() {
    'use strict';

    function validExpression(text) {
        return Boolean(text && text.trim() !== '' && text.match(/[+-]?[\d\.]+%?/));
    }

    function calculationMethod(exp) {
        if (exp[0] == '+' || (exp[exp.length - 1] == '%' && exp[0] != '-')) {
            if (exp[exp.length - 1] == '%') {
                return function(a, b) {
                    return a + (a * (b / 100));
                };
            } else {
                return function(a, b) {
                    return a + b;
                };
            }
        } else if (exp[0] == '-') {
            if (exp[exp.length - 1] == '%') {
                return function(a, b) {
                    return a - (a * (b / 100));
                };
            } else {
                return function(a, b) {
                    return a - b;
                };
            }
        } else if (/[0-9]/.test(exp[0])) {
            return function fixed(a, b) {
                return b;
            };
        } else {
            return null;
        }
    }

    function calculateVariantProperty(prop, exp) {
        $(products).each(function(i, product) {
            $(product.variants).each(function(j, variant) {
                var original_price = original_products[i].variants[j][prop];
                var formula = calculationMethod(exp);
                if (formula && (original_price || typeof(original_price) === 'number')) {
                    if (formula) {
                        var expression = parseFloat(exp.replace(/[%\+\$-]/g, ''));
                        variant[prop] = Math.max(formula(parseFloat(original_price), expression), 0.0).toFixed(2);
                    }
                }
            });
        });
    }

    function changeVariantProperty(prop, value) {
        $(products).each(function(i, product) {
            $(product.variants).each(function(j, variant) {
                if (variant[prop] !== '') {
                    variant[prop] = value;
                }
            });
        });
    }

    function resetVariantProperty(prop) {
        $(products).each(function(i, product) {
            $(product.variants).each(function(j, variant) {
                if (variant[prop] !== '') {
                    variant[prop] = original_products[i].variants[j][prop];
                }
            });
        });
    }

    Vue.component('bulk-edit-table', {
        template: '#bulk-edit-table-tpl',
        props: ['products'],
        data: function() {
            return {
                task_ids: null,
                save_btn: null
            };
        },
        created: function() {
            this.pusherSub();
        },
        methods: {
            pusherSub: function() {
                if (typeof(Pusher) === 'undefined') {
                    toastr.error('This could be due to using Adblocker extensions<br>' +
                        'Please whitelist Dropified website and reload the page<br>' +
                        'Contact us for further assistance',
                        'Pusher service is not loaded', {
                            timeOut: 0
                        });
                    return;
                }

                var pusher = new Pusher(sub_confs[0].key);
                var vm = this;
                for (var i = 0; i < sub_confs.length; i++) {
                    var sub_conf = sub_confs[i];
                    var channel = pusher.subscribe(sub_conf.channel);

                    channel.bind('bulk-edit-connected', function(data) {
                        if (data.task in vm.task_ids) {
                            vm.task_ids[data.task] = data;
                            var completed = true;
                            for (var task_id in vm.task_ids) {
                                if (vm.task_ids.hasOwnProperty(task_id) && !vm.task_ids[task_id]) {
                                    completed = false;
                                }
                            }
                            if (completed) {
                                vm.savingChangesCompleted(vm.task_ids);
                            }
                        }
                    });
                }
            },
            saveChanges: function(e) {
                this.save_btn = $(e.target);
                this.save_btn.button('loading');
                this.task_ids = {};

                toastr.clear();

                var api_data = {};
                $.map(this.products, function(el) {
                    if (!api_data[el.store]) {
                        api_data[el.store] = [];
                    }
                    api_data[el.store].push({
                        'id': el.id,
                        'title': el.title,
                        'product_type': el.product_type,
                        'tags': el.tags,
                        'vendor': el.vendor,
                        'variants': $.map(el.variants, function(variant) {
                            return {
                                'id': variant.id,
                                'price': variant.price,
                                'compare_at_price': variant.compare_at_price,
                                'weight': variant.weight,
                                'weight_unit': variant.weight_unit,
                            };
                        })
                    });
                });

                for (var store in api_data) {
                    if (api_data.hasOwnProperty(store)) {
                        $.ajax({
                            url: '/api/bulk-edit-connected',
                            type: 'POST',
                            data: JSON.stringify({
                                products: api_data[store],
                                store: store
                            }),
                            contentType: "application/json; charset=utf-8",
                            dataType: "json",
                            context: {
                                vm: this
                            },
                            success: function(data) {
                                this.vm.task_ids[data.task] = false;
                            },
                            error: function(data) {
                                displayAjaxError('Bulk Edit', data);
                                this.vm.save_btn.button('reset');
                            }
                        });
                    }
                }
            },
            savingChangesCompleted: function(task_ids) {
                toastr.success('Changes saved!', 'Bulk Edit');
                this.save_btn.button('reset');

                for (var task_id in task_ids) {
                    if (task_ids.hasOwnProperty(task_id)) {
                        var data = task_ids[task_id];
                        if (data.errors && data.errors.length) {
                            toastr.options.closeButton = true;
                            toastr.options.newestOnTop = false;
                            toastr.options.timeOut = 0;
                            toastr.options.extendedTimeOut = 0;

                            toastr.error('An error occured will updating the following Products:');

                            $.each(data.errors, function(i, title) {
                                toastr.error(title);
                            });
                        }
                    }
                }
            }
        }
    });

    Vue.component('product-row', {
        template: '#product-row-tpl',
        props: ['product'],
    });

    Vue.component('variant-row', {
        template: '#variant-row-tpl',
        props: ['product', 'variant'],
    });

    Vue.component('bulk-edit-inputs', {
        template: '#bulk-edit-inputs-tpl',
        props: ['products'],
        methods: {
            onExpChange: function(e) {
                var exp = e.target.value;
                var prop = e.target.dataset.calc;

                if (['weight_unit'].indexOf(prop) !== -1) {
                    changeVariantProperty(prop, exp);
                } else if (validExpression(exp)) {
                    calculateVariantProperty(prop, exp);
                } else {
                    resetVariantProperty(prop);
                }
            }
        },
    });

    // create the root instance
    new Vue({
        el: '#bulk-edit',
        data: {
            products: products
        }
    });

})();