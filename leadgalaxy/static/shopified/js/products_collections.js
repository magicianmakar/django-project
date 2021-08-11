(function() {
    'use strict';

    var initForms = false;
    var loadingContainer = document.querySelector("#page-wrapper > div.wrapper.wrapper-content > div");

    function changeHashUrl(param) {
        location.hash = encodeURIComponent(btoa(JSON.stringify(param)));
    }

    function getHashUrl() {
        try {
            return JSON.parse(atob(decodeURIComponent(location.hash).replace(/^#/, '')));
        } catch (e) {
            return null;
        }
    }

    function catIdFromUrl(url) {
        try {
            return url.match(/category\/([0-9]+)/).pop();
        } catch (e) {
            return null;
        }
    }

    $('.open-category').click(function(e) {
        e.preventDefault();

        var btn = $(e.currentTarget);
        var url = btn.data('url');
        var catId = catIdFromUrl(url);


        $('#product-search-cat option').filter(function(i, el) {
            return catIdFromUrl($(el).val()) === catId;
        }).prop('selected', 'selected');

        changeHashUrl({
            category: catId,
        });
    });

    $('#product-search-btn').click(function(e) {
        e.preventDefault();

        var searchSort = $('#product-search-sort option:selected').val();
        var searchText = encodeURIComponent($('#product-search-input').val());
        var category = '';
        var shipFrom = $('#product-search-shipfrom option:selected').val();
        var freeShipping = $('#product-search-freeship').is(':checked') ? 'y' : 'n';
        var priceMin = $('#product-search-pricemin').val();
        var priceMax = $('#product-search-pricemax').val();

        try {
            if ($('#product-search-cat option:selected').val()) {
                category = catIdFromUrl($('#product-search-cat option:selected').val());
            }
        } catch (e) {}

        if (searchText.length || category.length) {
            changeHashUrl({
                category: category,
                search: searchText,
                sort: searchSort,
                shipFrom: shipFrom,
                freeShipping: freeShipping,
                priceMin: priceMin,
                priceMax: priceMax,
                _: $.now(),
            });
        } else {
            location.hash = '';
        }
    });

    $('.update-on-change').keyup(function(e) {
        if (e.keyCode == 13) {
            $('#product-search-btn').trigger('click');
        }
    });

    $('.update-on-change').on('change ifChanged', function (e) {
        if(location.hash) {
            $('#product-search-btn').trigger('click');
        }
    });

    function showCategory() {
        if (!window.extensionSendMessage) {
            swal('Please reload the page and make sure you are using the latest version of the extension.');
            return;
        }

        $(loadingContainer).LoadingOverlay("show", {
            background: "rgba(200, 200, 200, 0.6)",
            zIndex: 9990
        });

        var requests_inprogress = $(loadingContainer).data('requests_inprogress')?$(loadingContainer).data('requests_inprogress'):0;
        $(loadingContainer).data('requests_inprogress',requests_inprogress+1);

        var info = getHashUrl();
        var extra = {
            shipFromCountry: info.shipFrom,
            isFreeShip: info.freeShipping,
        };

        if(info.priceMin) {
            extra.minPrice = info.priceMin;
        }

        if (info.priceMax) {
            extra.maxPrice = info.priceMax;
        }

        if (info.page) {
            extra.page = info.page;
        }

        window.extensionSendMessage({
            subject: 'aliexpressProductSearch',
            from: 'website',
            catId: info.category,
            searchText: info.search,
            searchSort: info.sort,
            extra: extra,
        }, function(rep) {

            var requests_inprogress = $(loadingContainer).data('requests_inprogress')?$(loadingContainer).data('requests_inprogress'):0;
            $(loadingContainer).data('requests_inprogress',requests_inprogress-1);

            if ($(loadingContainer).data('requests_inprogress')<=0)
                {$(loadingContainer).LoadingOverlay("hide", true);}

            if (!rep.success) {
                swal('Products Database', 'Could not get products list, please try again', 'error');
                return;
            }

            // if no items in array, try to fetch them from itemList
            if (rep.data.items && !rep.data.items.length && rep.data.mods && rep.data.mods.itemList.content.length) {
                // try to make list from mods.itemList and support both V3 and old format
                $.each(rep.data.mods.itemList.content, function (i, item) {
                    var item_obj = {};
                    if (item.itemType=='productV3'){
                        item_obj={
                        imageUrl: item.image.imgUrl,
                        productDetailUrl: "https://www.aliexpress.com/item/"+item.productId+".html",
                        productId: item.productId,
                        price: item.prices.salePrice.formattedPrice,
                        title: item.title.displayTitle,
                        tradeDesc: (item.trade?item.trade.tradeDesc:''),
                        logisticsDesc: (item.logistics?item.logistics.logisticsDesc:''),
                        store: item.store,
                        starRating: (item.evaluation?item.evaluation.starRating:false)
                        };
                    }
                    else {
                        item_obj={
                        imageUrl: item.image.imageUrl,
                        productDetailUrl: "https://www.aliexpress.com/item/"+item.productId+".html",
                        productId: item.productId,
                        price: item.prices.sale_price.formattedPrice,
                        title: item.title.displayTitle,
                        tradeDesc: (item.trade?item.trade.tradeDesc:''),
                        logisticsDesc: (item.logistics?item.logistics.logisticsDesc:''),
                        store: item.store,
                        starRating: (item.evaluation?item.evaluation.starRating:false)
                        };
                    }
                    rep.data.items.push(item_obj);
                });
            }

            var produtcTpl = Handlebars.compile($("#products-collection-product-template").html());

            $('.products-list').empty();

            if (rep.data.refineShipFromCountries) {
                $('#product-search-shipfrom option').filter(function(i, el) {
                    return $(el).val() !== 'US';
                }).attr('disabled', 'disabled');

                $.each(rep.data.refineShipFromCountries, function (i, el) {
                    $('#product-search-shipfrom option').filter(function(j, opt) {
                        return $(opt).val() === el.countryCode;
                    }).removeAttr('disabled');
                });
            }

            if (!rep.data.items || !rep.data.items.length) {
                var countryName = '';

                if(extra.shipFromCountry) {
                    var matchCountry = $('#product-search-shipfrom option').filter(function(i, el) {
                        return $(el).val() === extra.shipFromCountry && !$(el).attr('disabled');
                    });


                    if(!matchCountry || !matchCountry.length) {
                        countryName = $('#product-search-shipfrom option').filter(function(i, el) {
                            return $(el).val() === extra.shipFromCountry;
                        }).text();
                    }
                }

                $('.products-list').append($('<h3 class="text-center" style="display:block;width: 100%;text-align: center;">' +
                    'Your search did not match any products.</h3>'));

                if(countryName.length) {
                    $('.products-list').append($('<h3 class="text-center" style="display:block;width: 100%;text-align: center;">' +
                        'Note: Try to change Your Aliexpress country to ' + countryName + '</h3>'));
                }
            } else {
                $.each(rep.data.items, function (i, item) {
                    if (!item.tradeDesc) {
                        item.tradeDesc = '0 order';
                    }

                    item.lowImageUrl = '/static/img/blank.gif';
                    item.imageUrl = item.imageUrl.replace(/_[0-9]+x[0-9]+[a-z]*\.([a-z]+)/, '_640x640.$1');

                    var productEl = $(produtcTpl({
                        item: item
                    }));

                    $('.products-list').append(productEl);
                });


                if(rep.data.resultCount > rep.data.resultSizePerPage) {
                    $('.products-list').append($('<button>', {
                        'text': 'Load More',
                        'class': 'btn btn-block btn-lg btn-success m-t',
                        'href': '#',
                        'click': function(e) {
                            e.preventDefault();

                            var info = getHashUrl();
                            info.page = info.page ? parseInt(info.page) + 1 : 2;

                            changeHashUrl(info);
                        }
                    }));
                }
            }

            $('.products-list').show();
            $('.category-list').hide();

            $('.unveil').unveil();

            $('#product-search-shipfrom option').removeAttr('disabled');

            window.scrollTo(0,0);
        });
    }

    $(window).hashchange(function(e) {
        var hash = location.hash;
        if (!hash.length) {
            $('.products-list').hide();
            $('.category-list').show();
        } else if (getHashUrl() !== null) {
            showCategory();
        }
    });

    isExtensionReady().then(function() {
        if (location.hash.length) {
            var info = getHashUrl();

            if(info.search && info.search.length) {
                $('#product-search-input').val(decodeURIComponent(info.search));
            }

            $('#product-search-cat option').filter(function(i, el) {
                return catIdFromUrl($(el).val()) === info.category;
            }).prop('selected', 'selected');

            $('#product-search-sort option').filter(function(i, el) {
                return $(el).val().indexOf(info.sort) !== -1;
            }).prop('selected', 'selected');

            $('#product-search-shipfrom option').filter(function(i, el) {
                return $(el).val().indexOf(info.shipFrom) !== -1;
            }).prop('selected', 'selected');

            $('#product-search-freeship').prop('checked', info.freeShipping);

            if (info.priceMin) {
                $('#product-search-pricemin').val(info.priceMin);
            }

            if (info.priceMax) {
                $('#product-search-pricemax').val(info.priceMax);
            }

            $(window).hashchange();
        }
    });
})();
