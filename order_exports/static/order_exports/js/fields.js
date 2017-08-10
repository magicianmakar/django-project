window.OrderExport = {
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
        // this.onStartingAtCreatedAt();
        this.onToggleUsername();
        this.onAddProductTitle();
        this.onRemoveProductTitle();
        this.onFindShopifyProductClick();
        this.onShopifyProductSelected();
        this.onFoundProductDeleteClick();
        this.onSubuserClick();
        this.onStoreChange();

        this.autocompleteVendor.init();

        $('input[name="daterange"]').daterangepicker();

        var clockpickerInput = $('input[name="schedule"]');
        clockpickerInput.clockpicker({
            autoclose: true,
            afterHourSelect: function () {
                $('input[name="schedule"]').clockpicker('done');
            }
        });

        $('#shopify-products-popover').popover({
            html: true,
            trigger: 'hover',
            content: function () {
                return '<img src="/static/img/shopify-products-list.png" width="600">';
            }
        });

        // Order export descriptions
        this.helpText.general.execute();
        this.helpText.orderFilters.execute();
        this.helpText.productFilters.execute();
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
        var OrderExport = this;
        $('input[name="previous_day"]').on('ifChecked', function() {
            $('#schedule .range').hide();
            $('#schedule .daily').show();
            $('input[name="receiver"]').parents('.form-group').show();
            $('input[name="starting_at"]').parents('.form-group').show();
            $('#vendor-login').show();
            window.OrderExport.helpText.general.fill.execute();
        });

        $('input[name="previous_day"]').on('ifUnchecked', function() {
            $('#schedule .range').show();
            $('#schedule .daily').hide();
            $('input[name="receiver"]').val('').parents('.form-group').hide();
            $('input[name="starting_at"]').val('').parents('.form-group').hide();
            $('#vendor-login').hide();
            window.OrderExport.helpText.general.fill.execute();
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
        var OrderExport = this;

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
        var foundProductsLength = window.OrderExport.foundProducts.data.length;

        for (var i = 0; i < foundProductsLength; i++) {
            var foundProduct = window.OrderExport.foundProducts.data[i];

            window.OrderExport.addFoundProduct(foundProduct);
        }

        window.OrderExport.updateFoundProducts();
    },
    addFoundProduct: function(foundProduct) {
        productElement = $(window.OrderExport.foundProducts.template({product: foundProduct}));

        window.OrderExport.foundProducts.list.append(productElement);
    },
    updateFields: function(select) {
        var data = select.next().find('.search-choice').map(function(key, value) {
            var index = parseInt($(this).find('.search-choice-close').attr('data-option-array-index'));

            return select.find('option:nth-child('+(index+1)+')').val();
        });

        window.OrderExport.updateList(select.parents('.form-group').next().find('.nestable'), data);
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

            if (listItem.length === 0) {
                list.append(this.createListItem(list, item));
            } else if (listItem.attr('data-id') != item) {
                listItem.after(this.createListItem(list, item));
            }
        }
    },
    deleteFoundProductById: function(productId) {
        var foundProductsLength = window.OrderExport.foundProducts.data.length;

        for (var i = 0; i < foundProductsLength; i++) {
            var foundProduct = window.OrderExport.foundProducts.data[i];
            if (foundProduct.product_id == productId) {
                window.OrderExport.foundProducts.data.splice(i, 1);
                break;
            }
        }
    },
    updateFoundProducts: function(foundProduct) {
        if (foundProduct) {
            window.OrderExport.foundProducts.data.push(foundProduct);
            window.OrderExport.addFoundProduct(foundProduct);
        }

        window.OrderExport.foundProducts.input.val(
            JSON.stringify(window.OrderExport.foundProducts.data)
        );

        window.OrderExport.helpText.productFilters.exactProductInput.event();
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
            if ($(this).val() !== '') {
                $('[name="vendor_username"]').val('');
                $('[name="vendor_email"]').val('');
            }
        });
        
        $('[name="vendor_username"]').on('keyup', function() {
            if ($(this).val() !== '') {
                $('[name="vendor_user"]').val('');
            }
        });

        $('[name="vendor_email"]').on('keyup', function() {
            if ($(this).val() !== '') {
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

            window.OrderExport.updateFoundProducts(foundProduct);
        };
    },
    onFoundProductDeleteClick: function() {
        window.OrderExport.foundProducts.list.on('click', '.delete-found-product', function() {
            var productId = $(this).attr('data-product-id');

            window.OrderExport.deleteFoundProductById(parseInt(productId));
            window.OrderExport.updateFoundProducts();

            $(this).parents('.product-item.row').remove();
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
                    return false;
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
                            var link = app_link(['accounts/register/', data.hash]);
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
                    }
                });
            });
        });
    },
    onStoreChange: function() {
        $('[name="store"]').on('change', function() {
            window.OrderExport.autocompleteVendor.destroy();
            window.OrderExport.autocompleteVendor.init();
        });
    },
    autocompleteVendor: {
        init: function() {
            $('[name="vendor"]').autocomplete({
                serviceUrl: '/autocomplete/supplier-name?' + $.param({store: $('[name="store"]').val()}),
                minChars: 1,
                deferRequestBy: 300,
                onSelect: function(suggestion) {
                    $('[name="vendor"]').val(suggestion.value);
                }
            });
        },
        destroy: function() {
            $('[name="vendor"]').autocomplete('destroy');
        }
    },
    helpText: {
        general: {
            execute: function() {
                window.OrderExport.helpText.general.descriptionInput.event();
                window.OrderExport.helpText.general.storeSelect.event();
                window.OrderExport.helpText.general.timeField.event();
                window.OrderExport.helpText.general.createdAtInput.event();
                window.OrderExport.helpText.general.fill.execute();
            },
            isPreviousDay: function() {
                // Only fill export time, created since and receiver e-mail if previous day is active
                return $('[name="previous_day"]').is(':checked');
            },
            descriptionInput: {
                event: function() {
                    $('[name="description"]').on('change', function() {
                        window.OrderExport.helpText.general.fill.description();
                    });
                },
                text: function() {
                    var value = $('[name="description"]').val(),
                        label = $('<span class="label">').text(value);

                    return ['Your ', label, ' export will'];
                }
            },
            storeSelect: {
                event: function() {
                    $('[name="store"]').on('change', function() {
                        window.OrderExport.helpText.general.fill.store();
                    });
                },
                text: function() {
                    var value = $('[name="store"] option:selected').text(),
                        label = $('<span class="label">').text(value),
                        startText = ' look for orders on ';

                    return [startText, label, ' store'];
                }
            },
            timeField: {
                event: function() {
                    $('[name="schedule"], [name="daterange"]').on('change', function() {
                        window.OrderExport.helpText.general.fill.time(true);
                    });
                },
                text: function() {
                    if (window.OrderExport.helpText.general.isPreviousDay()) {
                        if (this.isEmpty()) {
                            return '';
                        }

                        var value = $('[name="schedule"]').val(),
                            label = $('<span class="label">').text(value);

                        return [', update everyday at ', label];
                    } else {
                        var value = $('[name="daterange"]').val().split('-'),
                            pre = $('<span class="label">').text(value[0]),
                            post = $('<span class="label">').text(value[1]);

                        return [', from ', pre, ' until ', post, '.'];
                    }
                },
                isEmpty: function() {
                    if (window.OrderExport.helpText.general.isPreviousDay()) {
                        return $('[name="schedule"]').val() == '';
                    }

                    return false;
                }
            },
            createdAtInput: {
                event: function() {
                    $('[name="starting_at"]').on('change', function() {
                        window.OrderExport.helpText.general.fill.createdAt(true);
                    });
                },
                text: function() {
                    if (!window.OrderExport.helpText.general.isPreviousDay()) {
                        return '';
                    }

                    var value = $('[name="starting_at"]').val();
                    if (value == '') {
                        var today = new Date().toISOString().slice(0, 10).split('-');
                        value = today[1] + '/' + today[2] + '/' + today[0];
                    }

                    var label = $('<span class="label">').text(value),
                        startWith = ', ';

                    if (!window.OrderExport.helpText.general.timeField.isEmpty()) {
                        startWith = ' and ';
                    }

                    return [startWith, 'starting with orders created at ', label, '.'];
                }
            },
            fill: {
                description: function() {
                    window.OrderExport.helpText.general.fill.common('.description',
                        window.OrderExport.helpText.general.descriptionInput.text());
                },
                store: function() {
                    window.OrderExport.helpText.general.fill.common('.store',
                        window.OrderExport.helpText.general.storeSelect.text());
                },
                time: function(createdAt) {
                    window.OrderExport.helpText.general.fill.common('.time',
                        window.OrderExport.helpText.general.timeField.text());

                    if (createdAt) {
                        window.OrderExport.helpText.general.fill.createdAt();
                    }
                },
                createdAt: function(time) {
                    window.OrderExport.helpText.general.fill.common('.created_at',
                        window.OrderExport.helpText.general.createdAtInput.text());

                    if (time) {
                        window.OrderExport.helpText.general.fill.time();
                    }
                },
                common: function(tagClass, newText) {
                    var placeholder = $('#export-description').find(tagClass);
                    placeholder.text('');
                    placeholder.append(newText);
                },
                execute: function() {
                    window.OrderExport.helpText.general.fill.description();
                    window.OrderExport.helpText.general.fill.store();
                    window.OrderExport.helpText.general.fill.time();
                    window.OrderExport.helpText.general.fill.createdAt();
                }
            }
        },
        orderFilters: {
            execute: function() {
                window.OrderExport.helpText.orderFilters.vendorInput.event();
                window.OrderExport.helpText.orderFilters.statusSelect.event();
                window.OrderExport.helpText.orderFilters.fulfillmentStatusSelect.event();
                window.OrderExport.helpText.orderFilters.financialStatusSelect.event();
                window.OrderExport.helpText.orderFilters.fill.execute();
            },
            textForSelect: function(selectName, checkComma) {
                var values = $(selectName+' option:selected').attr('data-explanation').match(/(.*)(\|.*)\|(.*)?/);
                if (values == null) {
                    return '';
                }

                var pre = values[1],
                    value = values[2].slice(1),
                    post = values[3];

                if (values[1][0] == '|') {
                    pre = '';
                    value = values[1].slice(1);
                    post = values[2];
                }
                if (!post) {
                    post = '';
                }

                var label = $('<span class="label">').text(value);
                if (checkComma) {
                    if ($(checkComma).val() != '') {
                        pre = ',' + pre;
                    }
                } else {
                    pre = ' and' + pre;
                }

                return [pre, label, post];
            },
            vendorInput: {
                event: function() {
                    $('[name="vendor"]').on('change', function() {
                        window.OrderExport.helpText.orderFilters.fill.vendor();
                    });
                },
                text: function() {
                    var value = $('[name="vendor"]').val();
                    if (value == '') {
                        return '';
                    }

                    var label = $('<span class="label">').text(value);

                    return [' for products having ', label, ' as partial or full vendor name'];
                }
            },
            statusSelect: {
                event: function() {
                    $('[name="status"]').on('change', function() {
                        window.OrderExport.helpText.orderFilters.fill.status();
                    });
                },
                text: function() {
                    return window.OrderExport.helpText.orderFilters.textForSelect('[name="status"]', '[name="vendor"]');
                }
            },
            fulfillmentStatusSelect: {
                event: function() {
                    $('[name="fulfillment_status"]').on('change', function() {
                        window.OrderExport.helpText.orderFilters.fill.fulfillmentStatus();
                    });
                },
                text: function() {
                    return window.OrderExport.helpText.orderFilters.textForSelect('[name="fulfillment_status"]', '[name="status"]');
                }
            },
            financialStatusSelect: {
                event: function() {
                    $('[name="financial_status"]').on('change', function() {
                        window.OrderExport.helpText.orderFilters.fill.financialStatus();
                    });
                },
                text: function() {
                    return window.OrderExport.helpText.orderFilters.textForSelect('[name="financial_status"]', null);
                }
            },
            fill: {
                vendor: function() {
                    window.OrderExport.helpText.orderFilters.fill.common('.vendor',
                        window.OrderExport.helpText.orderFilters.vendorInput.text());

                    window.OrderExport.helpText.orderFilters.fill.status();
                },
                status: function() {
                    window.OrderExport.helpText.orderFilters.fill.common('.status',
                        window.OrderExport.helpText.orderFilters.statusSelect.text());
                },
                fulfillmentStatus: function() {
                    window.OrderExport.helpText.orderFilters.fill.common('.fulfillment',
                        window.OrderExport.helpText.orderFilters.fulfillmentStatusSelect.text());
                },
                financialStatus: function() {
                    window.OrderExport.helpText.orderFilters.fill.common('.financial',
                        window.OrderExport.helpText.orderFilters.financialStatusSelect.text());
                },
                common: function(tagClass, newText) {
                    var placeholder = $('#order-filters-description').find(tagClass);
                    placeholder.text('');
                    placeholder.append(newText);
                },
                execute: function() {
                    window.OrderExport.helpText.orderFilters.fill.vendor();
                    window.OrderExport.helpText.orderFilters.fill.status();
                    window.OrderExport.helpText.orderFilters.fill.fulfillmentStatus();
                    window.OrderExport.helpText.orderFilters.fill.financialStatus();
                }
            }
        },
        productFilters: {
            empty: true,
            execute: function() {
                window.OrderExport.helpText.productFilters.checkEmpty();
                window.OrderExport.helpText.productFilters.priceRangeInput.event();
                window.OrderExport.helpText.productFilters.titleContainInput.event();
                window.OrderExport.helpText.productFilters.fill.execute();
            },
            checkEmpty: function() {
                var titles = window.OrderExport.helpText.productFilters.titleContainInput.getTitles(),
                    priceMin = $('[name="product_price_min"]').val(),
                    priceMax = $('[name="product_price_max"]').val(),
                    products = window.OrderExport.foundProducts.data;
                
                if (titles.length == 0 && priceMin == '' && priceMax == '' && products.length == 0) {
                    $('#product-filters-description').parents('.alert.alert-success').addClass('hidden');
                    this.empty = true;
                } else {
                    $('#product-filters-description').parents('.alert.alert-success').removeClass('hidden');
                    this.empty = false;
                }
            },
            priceRangeInput: {
                event: function() {
                    $('[name="product_price_min"], [name="product_price_max"]').on('change', function() {
                        window.OrderExport.helpText.productFilters.fill.priceRange();
                    });
                },
                text: function() {
                    var minValue = $('[name="product_price_min"]').val(),
                        maxValue = $('[name="product_price_max"]').val(),
                        result = [];

                    if (minValue) {
                        result.push(' starting at price of ');
                        result.push($('<span class="label">').text(minValue));
                    }

                    if (maxValue) {
                        if (result.length > 0) {
                            result.push(' and');
                        }
                        result.push(' ending at price of ');
                        result.push($('<span class="label">').text(maxValue));
                    }

                    if (result.length > 0) {
                        result.unshift('Filter orders by products');
                        result.push('.');

                        if (window.OrderExport.helpText.productFilters.empty) {
                            window.OrderExport.helpText.productFilters.checkEmpty();
                        }
                    } else {
                        window.OrderExport.helpText.productFilters.checkEmpty();
                    }

                    return result;
                }
            },
            titleContainInput: {
                event: function() {
                    $('#product-title-contains').on('change', '[name="product_title"]', function() {
                        window.OrderExport.helpText.productFilters.fill.titleContain();
                    });
                },
                text: function() {
                    var titles = this.getTitles();

                    if (titles.length == 0) {
                        window.OrderExport.helpText.productFilters.checkEmpty();
                        return '';
                    }

                    if (window.OrderExport.helpText.productFilters.empty) {
                        window.OrderExport.helpText.productFilters.checkEmpty();
                    }

                    var result = [];
                    if ($('[name="product_price_min"]').val() != '' && $('[name="product_price_max"]').val() != '') {
                        result.push($('<br>'));
                    }
                    result.push('Your search will be restricted by products that contains the full or partial name(s): ');

                    for (var i = 0, iLength = titles.length; i < iLength; i++) {
                        var title = $('<span class="label">').text(titles[i]);

                        if (i > 0) {
                            result.push(', ');
                        }
                        result.push(title);
                    }
                    result.push('.');

                    return result;
                },
                getTitles: function() {
                    return $('[name="product_title"]').map(function(key, element) {
                        var value = $(element).val();
                        if (value) return value;
                    }).get();
                }
            },
            exactProductInput: {
                event: function() {
                    window.OrderExport.helpText.productFilters.fill.exactProduct();
                },
                text: function() {
                    if (window.OrderExport.foundProducts.data.length == 0) {
                        window.OrderExport.helpText.productFilters.checkEmpty();
                        return ''
                    } else {
                        if (window.OrderExport.helpText.productFilters.empty) {
                            window.OrderExport.helpText.productFilters.checkEmpty();
                        }

                        var result = [];
                        if (window.OrderExport.helpText.productFilters.titleContainInput.getTitles().length == 0) {
                            if ($('[name="product_price_min"]').val() != '' && $('[name="product_price_max"]').val() != '') {
                                result.push($('<br>'));
                            }

                            result.push('Your search will be restricted by products from the list above.');
                        } else {
                            result.push($('<br>'));
                            result.push('Or by exact products from the list above.');
                        }

                        return result;
                    }
                }
            },
            fill: {
                priceRange: function() {
                    window.OrderExport.helpText.productFilters.fill.common('.price-range',
                        window.OrderExport.helpText.productFilters.priceRangeInput.text());

                    window.OrderExport.helpText.productFilters.fill.titleContain();
                },
                titleContain: function() {
                    window.OrderExport.helpText.productFilters.fill.common('.product-contains',
                        window.OrderExport.helpText.productFilters.titleContainInput.text());

                    window.OrderExport.helpText.productFilters.fill.exactProduct();
                },
                exactProduct: function() {
                    window.OrderExport.helpText.productFilters.fill.common('.exact-product',
                        window.OrderExport.helpText.productFilters.exactProductInput.text());
                },
                common: function(tagClass, newText) {
                    var placeholder = $('#product-filters-description').find(tagClass);
                    placeholder.text('');
                    placeholder.append(newText);
                },
                execute: function() {
                    window.OrderExport.helpText.productFilters.fill.priceRange();
                    window.OrderExport.helpText.productFilters.fill.titleContain();
                    window.OrderExport.helpText.productFilters.fill.exactProduct();
                }
            }
        }
    }
};

$(function() {
    window.OrderExport.init();
});
