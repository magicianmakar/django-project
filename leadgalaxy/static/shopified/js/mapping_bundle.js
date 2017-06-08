(function(store_id, product_id, shopify_product, bundle_mapping) {
    'use strict';

    function formatRepo(repo) {
        if (repo.loading) {
            return repo.text;
        }

        return '<span><img src="' + repo.image +
            '"><a href="#">' +
            repo.text.replace('"', '\'') + '</a></span>';
    }

    function formatRepoSelection(repo) {
        return repo.text;
    }


    var truncate = function(text, length, clamp) {
        clamp = clamp || '...';
        length = length || 60;
        var node = document.createElement('div');
        node.innerHTML = text;
        var content = node.textContent;
        return content.length > length ? content.slice(0, length) + clamp : content;
    };

    Vue.filter('truncate', truncate);

    Vue.component('bundle-mapping-table', {
        template: '#bundle-mapping-table-tpl',
        props: ['variants'],
        data: function() {
            return {
                save_btn: null
            };
        },
        created: function() {},
        methods: {
            saveChanges: function(e) {
                this.save_btn = $(e.target);
                this.save_btn.bootstrapBtn('loading');

                toastr.clear();

                var api_data = {};

                $.map(bundle_mapping, function(el) {
                    api_data[el.id] = el.products;
                });

                $.ajax({
                    url: '/api/bundles-mapping',
                    type: 'POST',
                    data: JSON.stringify({
                        mapping: api_data,
                        product: product_id,
                    }),
                    contentType: "application/json; charset=utf-8",
                    dataType: "json",
                    context: {
                        vm: this
                    },
                    success: function(data) {
                        toastr.success('Bundle Mapping', 'Mapping Saved');

                        setTimeout(function() {
                            window.location.reload();
                        }, 500);
                    },
                    error: function(data) {
                        displayAjaxError('Bundle Mapping', data);
                    },
                    complete: function() {
                        this.vm.save_btn.bootstrapBtn('reset');
                    }
                });
            }
        }
    });

    Vue.component('variant-row', {
        template: '#variant-row-tpl',
        props: ['variants', 'variant', 'variant_idx'],
    });

    Vue.component('product-row', {
        template: '#product-row-tpl',
        props: ['product', 'product_idx', 'variant'],
        methods: {
            removeProduct: function (e) {
                this.variant.products.splice(this.product_idx, 1);
            }
        }
    });

    Vue.component('add-product-row', {
        template: '#add-product-row-tpl',
        props: ['variant'],
        data: function() {
            return {
                showControls: false,
                variantInput: false,
                quantityInput: false,
                canSave: false,
                initSelect: true,
                new_product: {}
            };
        },
        methods: {
            showSelection: function(e) {
                e.preventDefault();

                this.showControls = !this.showControls;
                var setupVariantSelection = this.setupVariantSelection;
                var $v = this;

                if (this.initSelect) {
                    $('.product-select', this.$el).click(function (e) {
                        $('#modal-shopify-product').prop('connected', true);
                        $('#modal-shopify-product').modal('show');

                        // Product Shopify Connect
                        window.shopifyProductSelected = function (store, shopify_id, product_data) {
                            if (!product_data.shopified) {
                                toastr.error('Product is not connected');
                                return;
                            }

                            setupVariantSelection(product_data.shopified);
                            $v.new_product = {
                                id: product_data.shopified,
                                title: product_data.title,
                                short_title: truncate(product_data.title, 40),
                                image: product_data.image,
                                variant_id: 0,
                                variant_title: '',
                                variant_image: null,
                            };

                            $('#modal-shopify-product').modal('hide');
                        };
                    });

                    this.initSelect = false;
                }
            },
            setupVariantSelection: function(product_id) {
                var $v = this;
                var el = this.$el;

                $('select.variant-select option', el).remove();
                $('select.variant-select', el).append($('<option>'));
                $('select.variant-select', el).trigger('change.select2');
                $('select.variant-select', el).prop('disabled', true);

                $.ajax({
                    url: '/autocomplete/variants',
                    type: 'GET',
                    data: {
                        store: store_id,
                        product: product_id,
                        term: '*'
                    },
                }).done(function (data) {
                    var variants = [];
                    $.map(data.suggestions, function(el) {
                        variants.push({
                            id: el.data,
                            text: el.value,
                            image: el.image || '//d2kadg5e284yn4.cloudfront.net/static/img/blank.gif',
                        });
                    });

                    $('select.variant-select', el).select2({
                        placeholder: 'Select a Variant',
                        data: variants,
                        escapeMarkup: function(markup) {
                            return markup;
                        },
                        minimumInputLength: 0,
                        templateResult: formatRepo,
                        templateSelection: formatRepoSelection
                    }).on('select2:select', function(e) {
                        $v.new_product.variant_id = e.params.data.id;
                        $v.new_product.variant_title = e.params.data.text;
                        $v.new_product.variant_image = e.params.data.image;
                    });

                    $('select.variant-select', el).prop('disabled', false);

                }).fail(function(data) {
                    displayAjaxError('Variants Selection', data);
                }).always(function() {
                });
            },
            saveSelection: function (e) {
                e.preventDefault();

                var $v = this;
                var el = this.$el;

                $v.new_product.quantity = parseInt($('input.quantity-value', el).val()) || 1;

                this.variant.products.push($v.new_product);

                this.resetSelector();
            },
            cancelSave: function (e) {
                e.preventDefault();

                this.resetSelector();
            },
            resetSelector: function() {
                $('select.product-select option', this.$el).remove();
                $('select.product-select', this.$el).trigger('change.select2');

                $('select.variant-select option', this.$el).remove();
                $('select.variant-select', this.$el).trigger('change.select2');

                $('input.quantity-value', this.$el).val('1');

                this.new_product = {};
                this.showControls = false;
            }
        }
    });

    // create the root instance
    new Vue({
        el: '#bundle-mapping-entry',
        data: {
            variants: bundle_mapping
        }
    });

})(store_id, product_id, shopify_product, bundle_mapping);