window.OrderExportAdd = {
    fieldsSelect: $('.chosen-select'),
    selectableFields: $('.selectable'),
    fieldsList: $('.nestable'),
    foundProducts: {
        data: window.foundProducts,
        list: $('#order-export-products .shopify-products'),
        input: $('input[name="found_products"]'),
        template: Handlebars.compile($("#product-found-template").html())
    },
    init: function() {
        this.initializeFieldsSelect();
        this.initializeFieldsList();
        this.renderFoundProducts();
        this.initializeDatepicker();

        // events
        this.onClickEdit();
        this.onUnselectField();
        this.onStartingAtCreatedAt();
        this.onToggleUsername();
        this.onAddProductTitle();
        this.onRemoveProductTitle();
        this.onFindShopifyProductClick();
        this.onShopifyProductSelected();
        this.onFoundProductDeleteClick();
        this.onAutocompleteVendor();
        this.onSubuserClick();
        this.onAutocompleteVendor();
        this.onSubuserClick();

        var clockpickerInput = $('input[name="schedule"]');
        clockpickerInput.clockpicker({
            autoclose: true,
            afterHourSelect: function(e) {
                clockpickerInput.clockpicker('done');
            }
        });
        clockpickerInput.on('change', function(e) {
            $(this).val($(this).val().replace(/(\d\d):(\d\d)/, '$1:00'));
        });

        $('input[name="daterange"]').daterangepicker();
    },
    initializeDatepicker: function() {
        $('.input-group.date').datepicker({
            todayBtn: "linked",
            keyboardNavigation: false,
            forceParse: false,
            calendarWeeks: true,
            autoclose: true
        });
    },
    onClickEdit: function() {
        $('.field-wrapper').hide();
        $('.edit').on('click', function(e) {
            e.preventDefault();
            $(this).parents('.nestable').siblings('.field-wrapper').show();
            $(this).hide();
        });
    },
    initializeFieldsSelect: function() {
        var OrderExportAdd = this;
        $('input[name="previous_day"]').on('ifChecked', function() {
            $('#schedule .range').hide();
            $('#schedule .daily').show();
            $('input[name="receiver"]').parents('.form-group').show();
            $('input[name="starting_at"]').parents('.form-group').show();
            $('#vendor-login').show();
        });

        $('input[name="previous_day"]').on('ifUnchecked', function() {
            $('#schedule .range').show();
            $('#schedule .daily').hide();
            $('input[name="receiver"]').val('').parents('.form-group').hide();
            $('input[name="starting_at"]').val('').parents('.form-group').hide();
            $('#vendor-login').hide();
        });

        this.selectableFields.on("ifChecked", function() {
            var self = this;
            $(this).parents('.icheck').fadeOut(200, function() {
                var wrapper = $(self).parents('.field-wrapper'),
                    list = wrapper.siblings('.nestable').find('.dd-list');

                list.find('a.edit').before(
                    $('<li data-id="'+$(self).attr('name')+'" class="dd-item">').append(
                        $('<div class="dd-handle">').append($(self).parents('.icheck'))
                    )
                );
                $(self).parents('.icheck').fadeIn(200);

                data = list.find('li').map(function(key, value) {
                    return $(value).attr('data-id');
                }).get();
                
                wrapper.siblings('.output').val(window.JSON.stringify(data));
            });

        }).on('ifUnchecked', function() {
            var ddItem = $(this).parents('.dd-item');
            $('.field-wrapper[data-name="'+$(this).attr('name')+'"]').html($(this).parents('.icheck'));
            ddItem.remove();

            var wrapper = $(this).parents('.field-wrapper'),
                list = wrapper.siblings('.nestable').find('.dd-list');

            data = list.find('li').map(function(key, value) {
                return $(value).attr('data-id');
            }).get();
            
            wrapper.siblings('.output').val(window.JSON.stringify(data));
        });
    },
    initializeFieldsList: function() {
        var OrderExportAdd = this;

        this.fieldsList.nestable({
            maxDepth: 1
        }).on('change', function (e) {
            var list = e.length ? e : $(e.target),
                output = list.data('output'),
                data = list.nestable('serialize');

            data = $(this).find('li').map(function(key, value) {
                return $(value).attr('data-id');
            }).get();
            
            output.val(window.JSON.stringify(data));
        });

        var updateOutput = function (e) {
            var list = e.length ? e : $(e.target),
                output = list.data('output');

            data = list.find('li').map(function(key, value) {
                return $(value).attr('data-id');
            }).get();
            
            output.val(window.JSON.stringify(data));
        };

        this.fieldsList.each(function() {
            updateOutput($(this).data('output', $(this).next('[type="hidden"]')));
        });
    },
    renderFoundProducts: function() {
        var foundProductsLength = window.OrderExportAdd.foundProducts.data.length;

        for (var i = 0; i < foundProductsLength; i++) {
            var foundProduct = window.OrderExportAdd.foundProducts.data[i];

            window.OrderExportAdd.addFoundProduct(foundProduct);
        }

        window.OrderExportAdd.updateFoundProducts();
    },
    addFoundProduct: function(foundProduct) {
        productElement = $(window.OrderExportAdd.foundProducts.template({product: foundProduct}));

        window.OrderExportAdd.foundProducts.list.append(productElement);
    },
    updateFields: function(select) {
        var data = select.next().find('.search-choice').map(function(key, value) {
            var index = parseInt($(this).find('.search-choice-close').attr('data-option-array-index'));

            return select.find('option:nth-child('+(index+1)+')').val();
        });

        OrderExportAdd.updateList(select.parents('.form-group').next().find('.nestable'), data);
    },
    onUnselectField: function() {
        $('.unselect').on('mousedown', function(e) {
            e.preventDefault();
            e.stopPropagation();

            var formGroup = $(this).parents('div.nestable').parents('.form-group').prev('.form-group'),
                selectValue = $(this).parents('li.dd-item').attr('data-id'),
                fieldIndex = formGroup.find('option[value="'+selectValue+'"]').index();

            formGroup.find('.search-choice-close[data-option-array-index="'+fieldIndex+'"]').trigger('click');
        }).on('click', function(e) {
            e.preventDefault();
        });
    },
    orderSelect: function(list, select) {
        var choices = select.next().find('.chosen-choices');
        for (var i = 0, iLength = list.length; i < iLength; i++) {
            var item = list[i].id,
                itemText = select.find('option[value="'+item+'"]').text(),
                found = choices.find('.search-choice').filter(function() {
                    return $(this).text().trim() == itemText;
                });
            choices.append(found);
        }
        choices.append(choices.find('.search-field'));
    },
    createListItem: function(list, id) {
        var text = list.parents('.form-group').prev('.form-group').find(
            'select option[value="'+id+'"]').text().trim();
        return $('<li class="dd-item" data-id="'+id+'">').append(
            $('<div class="dd-handle">').append(
                text, 
                $('<a href="#" class="unselect close">').append(
                    $('<i class="fa fa-times">')
                )
            )
        );
    },
    updateList: function(list, data) {
        list = list.find('.dd-list');
        list.children().remove();

        for (var i = 0, iLength = data.length; i < iLength; i++) {
            var item = data[i],
                listItem = list.find('li:nth-child('+i+')');

            if (listItem.length == 0) {
                list.append(this.createListItem(list, item));
            } else if (listItem.attr('data-id') != item) {
                listItem.after(this.createListItem(list, item));
            }
        }
    },
    deleteFoundProductById: function(productId) {
        var foundProductsLength = window.OrderExportAdd.foundProducts.data.length;

        for (var i = 0; i < foundProductsLength; i++) {
            var foundProduct = window.OrderExportAdd.foundProducts.data[i];
            if (foundProduct.product_id == productId) {
                window.OrderExportAdd.foundProducts.data.splice(i, 1);
                break;
            }
        }
    },
    updateFoundProducts: function(foundProduct) {
        if (foundProduct) {
            window.OrderExportAdd.foundProducts.data.push(foundProduct);
            window.OrderExportAdd.addFoundProduct(foundProduct);
        }

        window.OrderExportAdd.foundProducts.input.val(
            JSON.stringify(window.OrderExportAdd.foundProducts.data)
        );
    },
    onStartingAtCreatedAt: function() {
        $('input[name="starting_at_boolean"]').on('ifChecked', function() {
            $('.starting-at-input').addClass('hidden');
            $('input[name="starting_at"]').val('');
        });

        $('input[name="starting_at_boolean"]').on('ifUnchecked', function() {
            $('.starting-at-input').removeClass('hidden');
        });
    },
    onToggleUsername: function() {
        $('[name="vendor_user"]').on('change', function() {
            if ($(this).val() != '') {
                $('[name="vendor_username"]').val('');
                $('[name="vendor_email"]').val('');
            }
        });
        
        $('[name="vendor_username"]').on('keyup', function() {
            if ($(this).val() != '') {
                $('[name="vendor_user"]').val('');
            }
        });

        $('[name="vendor_email"]').on('keyup', function() {
            if ($(this).val() != '') {
                $('[name="vendor_user"]').val('');
            }
        });
    },
    onAddProductTitle: function() {
        $('.add-product-title').on('click', function(e) {
            e.preventDefault();

            var productTitle = $('.product-title-clone').clone();
            productTitle.removeClass('product-title-clone');
            $('#product-title-contains').append(productTitle);

            var input = productTitle.find('input[name="product_title_clone"]');
            input.attr('name', input.attr('name').replace('_clone', ''));
            input.trigger('focus');
        });
    },
    onRemoveProductTitle: function() {
        $('#product-title-contains').on('click', '.remove-product-title', function(e) {
            e.preventDefault();

            $(this).parents('.product-title').remove();
        });
    },
    onFindShopifyProductClick: function() {
        $('.find-shopify-product').on('click', function(e) {
            e.preventDefault();

            $('#modal-shopify-product .shopify-store').val($('select[name="store"]').val());
            $('#modal-shopify-product').modal('show');
        });
    },
    onShopifyProductSelected: function() {
        window.shopifyProductSelected = function (store, shopify_id, product_data) {
            var foundProduct = {
                product_id: shopify_id,
                title: product_data.title,
                image_url: product_data.image
            };

            window.OrderExportAdd.updateFoundProducts(foundProduct);
        }
    },
    onFoundProductDeleteClick: function() {
        window.OrderExportAdd.foundProducts.list.on('click', '.delete-found-product', function() {
            var productId = $(this).attr('data-product-id');

            window.OrderExportAdd.deleteFoundProductById(parseInt(productId));
            window.OrderExportAdd.updateFoundProducts();

            $(this).parents('.product-item.row').remove();
        });
    },
    onAutocompleteVendor: function() {
        $('[name="vendor"]').autocomplete({
            serviceUrl: '/order/exports/vendor-autocomplete',
            minChars: 1,
            deferRequestBy: 500
        });
    },
    onSubuserClick: function() {
        $('.invite-subuser').click(function () {
            var btn = $(this);

            swal({
                title: "Add Sub User",
                text: "Add new sub user to your account",
                type: "input",
                showCancelButton: true,
                closeOnConfirm: false,
                closeOnCancel: true,
                animation: "slide-from-top",
                inputPlaceholder: "Email address",
                showLoaderOnConfirm: true
            }, function(inputValue) {
                if (inputValue === false) {
                    return;
                }

                if (inputValue === '' || inputValue.trim() === '') {
                    swal.showInputError("Email is required");
                    return false
                }

                $.ajax({
                    url: '/api/subuser-invite',
                    type: 'POST',
                    data: {
                        'email': inputValue
                    },
                    context: {btn: btn},
                    success: function (data) {
                        if (data.status == 'ok') {
                            var link = 'https://app.shopifiedapp.com/accounts/register/';
                            link += data.hash;
                            var msg = 'An email has been sent to the entred address with the following registration link:<br/>'+
                                      '<a href="'+link+'" style="word-wrap: break-word">'+link+'</a>';

                            swal({
                                title: 'Invitation Sent',
                                text: msg,
                                type: 'success',
                                html: true,
                            }, function(r) {
                                setTimeout(function() {
                                    window.location.reload();
                                }, 500);
                            });
                        } else {
                            displayAjaxError('Add Sub User', data);
                        }
                    },
                    error: function (data) {
                        displayAjaxError('Add Sub User', data);
                    },
                    complete: function () {
                    }
                });
            });
        });
    }
};

$(function() {
    window.OrderExportAdd.init();
});
