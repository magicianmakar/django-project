/*jshint esversion: 8 */
// 'use strict';
/* global $, toastr, swal, CKEDITOR */

var taskIntervals = {};
var taskCallsCount = {};

$(function () {
    var ui_update_popup = localStorage.getItem('ui_update_popup');
    if (!ui_update_popup) {
        if (window.is_old_layout) {
            $('#modal-ui-update').modal('show');
        }
        localStorage.setItem('ui_update_popup', true);
    }
});

$('body').on('click', '#update-ui-btn', function (){
    $.ajax({
        type: 'POST',
        url: '/api/user-show-new-layout',
        success: function (data) {
            window.location.reload();
        },
        error: function (data) {
            displayAjaxError('Update to New Flow', data);
        }
    });
});

$('body').on('click', '#open-support-chat', function (){
    $('.intercom-launcher').click();
});

$('body').on('click', '.menu-not-available', function (e){
    e.preventDefault();
    $('#upsell-modal').modal('show');
});

function isExtensionReady() {
    var $deferred = $.Deferred();

    var timerId = setInterval(function() {
        if (typeof window.extensionSendMessage === 'function') {
            $deferred.resolve();
            clearInterval(timerId);
        }
    }, 1000);

    setTimeout(function() {
        if (typeof window.extensionSendMessage !== 'function') {
            $deferred.reject();
            clearInterval(timerId);
        }
    }, 5000);

    return $deferred.promise();
}

function renderSupplierInfo(product_url, parent) {
    if ((/aliexpress.(com|us)/i).test(product_url)) {
        var product_id = product_url.match(/[\/_]([0-9]+)\.html/);
        if(!product_id || product_id.length != 2) {
            return;
        } else {
            product_id = product_id[1];
        }

        $('.product-original-link-loading', parent).show();

        window.extensionSendMessage({
            subject: 'ProductStoreInfo',
            product: product_id,
        }, function(rep) {
            $('.product-original-link-loading', parent).hide();

            if (rep && rep.name) {
                $('.product-supplier-name', parent).val(rep.name);
                $('.product-supplier-link', parent).val(rep.url);
            }
        });
    } else if ((/ebay/i).test(product_url)) {
        var site = 'global';
        if ((/ebay.com.au/i).test(product_url)) {
            site = 'au';
        } else if ((/ebay.de/i).test(product_url)) {
            site = 'de';
        } else if ((/ebay.fr/i).test(product_url)) {
            site = 'fr';
        } else if ((/ebay.co.uk/i).test(product_url)) {
            site = 'uk';
        } else if ((/ebay.ca/i).test(product_url)) {
            site = 'ca';
        }
        var ebay_product_id = product_url.match(/[\/_]([0-9]+)/g);
        if(!ebay_product_id || !ebay_product_id.length) {
            return;
        } else {
            if (ebay_product_id.length === 2) {
                ebay_product_id = ebay_product_id[1];
            } else {
                ebay_product_id = ebay_product_id[0];
            }
        }

        $('.product-original-link-loading', parent).show();

        window.extensionSendMessage({
            subject: 'ProductStoreInfoEbay',
            product: ebay_product_id,
            site: site,
        }, function(rep) {
            $('.product-original-link-loading', parent).hide();

            if (rep && rep.name) {
                $('.product-supplier-name', parent).val(rep.name);
                $('.product-supplier-link', parent).val(rep.url);
            }
        });
    } else if ((/print-on-demand/i).test(product_url)) {
        $.ajax({
            url: product_url + '?supplier=1',
            type: 'GET',
            beforeSend: function() {
                $('.product-original-link-loading', parent).show();
            },
            success: function(data) {
                $('.product-original-link-loading', parent).hide();

                if (data.success) {
                    $('.product-supplier-name', parent).val(data.name);
                    $('.product-supplier-link', parent).val(data.url);
                }
            }
        });
    } else if ((/dropified.com\/supplements\/usersupplement/i).test(product_url)) {
        $('.product-supplier-name', parent).val('Supplements on Demand');
    } else if (/alibaba.com/.test(product_url)) {
        $.ajax({
            type: 'GET',
            url: api_url('product-data', 'alibaba'),
            data: {'product_id': product_url.match(/(\d+)\.html/)[1]},
            beforeSend: function() {
                $('.product-original-link-loading', parent).show();
            },
            success: function(data) {
                $('.product-original-link-loading', parent).hide();
                $('.product-supplier-name', parent).val(data.store.name);
                $('.product-supplier-link', parent).val(data.store.url);
            }
        });
    }
}

function api_url(endpoint, store_type) {
    store_type = typeof(store_type) === 'undefined' ? null : store_type;

    var url = '';

    if(typeof(endpoint) === 'object') {
        endpoint = endpoint.reduce(function(a, b) {
            return a.replace(/\/+$/, '').replace(/^\/+/, '') + '/' + b.replace(/\/+$/, '').replace(/^\/+/, '');
        });
    }

    endpoint = endpoint.replace(/^\/?api\//, '');

    if (store_type) {
        url = '/api/' + store_type + '/' + endpoint;
    } else {
        url = '/api/' + endpoint;
    }

    return url;
}

function app_link(page, query) {
    var url = window.app_base_link;

    if (page) {
        if (Array.isArray(page)) {
            page = page.reduce(function(a, b) {
                return String(a).replace(/\/+$/, '').replace(/^\/+/, '') + '/' + String(b).replace(/\/+$/, '').replace(/^\/+/, '');
            });
        }

        url = url + '/' + page.replace(/\/+$/, '').replace(/^\/+/, '');
    }

    if (query) {
        url = url + '?' + $.param(query);
    }

    return url;
}

function allPossibleCases(arr, top) {
    top = typeof(top) === 'undefined' ? true : top;

    var sep = new Array(10).join('-');
    if (arr.length === 0) {
        return [];
    } else if (arr.length === 1) {
        return arr[0];
    } else {
        var result = [];
        var allCasesOfRest = allPossibleCases(arr.slice(1), false);
        for (var c in allCasesOfRest) {
            for (var i = 0; i < arr[0].length; i++) {
                result.push(arr[0][i] + sep + allCasesOfRest[c]);
            }
        }

        return top ? result.map(function(i) {
            return i.split(sep);
        }) : result;
    }
}

function displayAjaxError(desc, data, useHtml) {
    useHtml = useHtml === undefined ? false : useHtml;
    var error_msg = 'Server error.';

    if (typeof (data.error) == 'string') {
        error_msg = data.error;
    } else if (data.responseJSON && typeof (data.responseJSON.error) == 'string') {
        error_msg = data.responseJSON.error;
    } else if (typeof (data) == 'string') {
        error_msg = data;
    }

    if (useHtml) {
        swal({ html:true, title: desc, text: error_msg, type: 'error'});
    } else {
        swal(desc, error_msg, 'error');
    }
}

function getAjaxError(data) {
    var error_msg = 'Server error.';

    if (typeof (data.error) == 'string') {
        error_msg = data.error;
    } else if (data.responseJSON && typeof (data.responseJSON.error) == 'string') {
        error_msg = data.responseJSON.error;
    } else if (typeof (data) == 'string') {
        error_msg = data;
    }

    return error_msg;
}

function cleanImageLink(link) {
    return link.replace(/\?[^\?]+$/, '');
}

function cleanUrlPatch(url) {
    return url.replace(/\?.*$/, '').replace(/#.*$/, '');
}

function getFileName(url) {
    return cleanUrlPatch(url).split('/').pop();
}

function getFileExt(url) {
    return getFileName(url).split('.').pop();
}

function cleanUrlPath(url) {
    return url.replace(/\?.*$/, '').replace(/#.*$/, '');
}

function hashText(s) {
    var hash = 0, i, chr, len;
    if (s.length === 0) {
        return hash;
    }

    for (i = 0, len = s.length; i < len; i++) {
        chr = s.charCodeAt(i);
        hash = ((hash << 5) - hash) + chr;
        hash |= 0; // Convert to 32bit integer
    }

    return hash;
}

function hashUrlFileName(s) {
    if (!(/^https?:/).test(s)) {
        s = 'http://' + s.replace(/^\/\//, '');
    }

    var url = cleanUrlPath(s);
    var ext = getFileExt(s);

    if (!(/(gif|jpe?g|png|ico|bmp)$/i).test(ext)) {
        ext = 'jpg';
    }

    var hash = 0,
        i, chr, len;

    if (url.length === 0) {
        return hash;
    }

    hash = hashText(url);

    return hash ? hash + '.' + ext : hash;

}

function replaceQueryParam(param, value) {
    var queryParameters = {}, queryString = location.search.substring(1),
    re = /([^&=]+)=([^&]*)/g, m;

    while (m = re.exec(queryString)) {
        queryParameters[decodeURIComponent(m[1])] = decodeURIComponent(m[2]);
    }

    queryParameters[param] = value;
    return '?' + jQuery.param(queryParameters);
}


function getQueryVariable(variable, url) {
    var query = '';
    if (url === undefined) {
        query = window.location.search.substring(1);
        if (query === '' && window.location.href.indexOf('#') != -1) {
            var parts = window.location.href.split('#');
            if (parts.length == 2) {
                query = parts[1];
            }
        }
    } else {
        query = url.split('?');
        if (query.length == 2) {
            query = query[1];
        } else {
            query = url.split('#');
            if (query.length == 2) {
                query = query[1];
            } else {
                query = url;
            }
        }
    }

    var vars = query.split('&');
    for (var i = 0; i < vars.length; i++) {
        var pair = vars[i].split('=');
        if (decodeURIComponent(pair[0]) == variable) {
            return decodeURIComponent(pair[1]);
        }
    }

    return null;
}

function csrfSafeMethod(method) {
    // these HTTP methods do not require CSRF protection
    return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
}

function sendProductToShopify (product, store_id, product_id, callback, callback_data) {
    if (!store_id || store_id.length === 0) {
        alert('Please choose a Shopify store first!');
        return;
    }

    var api_data = {
      "product": {
        "title": product.title,
        "body_html": product.description,
        "product_type": product.type,
        "vendor": product.vendor,
        "published": $('#send-product-visible').prop('checked') || false,
        "tags": product.tags,
        "variants": [],
        "options": [],
        "images" :[]
      }
    };

    if (product.images) {
        for (var i = 0; i < product.images.length; i++) {
            var image = {
                src: product.images[i]
            };

            var imageFileName = hashUrlFileName(image.src);
            if (product.variants_images && product.variants_images.hasOwnProperty(imageFileName)) {
                image.filename = 'v-'+product.variants_images[imageFileName]+'__'+imageFileName;
            }

            api_data.product.images.push(image);
        }
    }

    product.weight = parseFloat(product.weight) || 0.0;

    if (product.variants.length === 0) {
        var vdata = {
            "price": product.price,
        };

        if (product.sku) {
            vdata.sku = product.sku;
        }

        if (product.compare_at_price) {
            vdata.compare_at_price = product.compare_at_price;
        }

        if (product.weight) {
            vdata.weight = product.weight;
            vdata.weight_unit = product.weight_unit;
        }

        api_data.product.variants.push(vdata);

    } else {
        $(product.variants).each(function (i, el) {
            api_data.product.options.push({
                'name': el.title,
                'values': el.values
            });
        });

        var vars_list = [];
        $(product.variants).each(function (i, el) {
            vars_list.push(el.values);
        });

        var variant_object_keys = [];
        var variant_info = '';
        if(product.hasOwnProperty('variants_info')) {
            variant_info = product.variants_info;
            if(typeof variant_info === 'object') {
                variant_object_keys = Object.keys(variant_info);
            }
        }

        if (vars_list.length>0) {
            vars_list = allPossibleCases(vars_list);

            for (var i=0; i<vars_list.length; i++) { // jshint ignore:line
                var title = vars_list[i].join ? vars_list[i].join(' & ') : vars_list[i];
                var alternate_title = vars_list[i].join ? vars_list[i].join(' / ') : vars_list[i];

                var vprice = product.price;
                var compare_at_price = '';
                if (product.compare_at_price) {
                    compare_at_price = product.compare_at_price;
                }

                if(variant_object_keys.length) {
                    if(variant_object_keys.includes(alternate_title)) {
                        vprice = variant_info[alternate_title].price;
                        if (product.compare_at_price) {
                            compare_at_price = variant_info[alternate_title].compare_at;
                        }
                    }
                }

                var vdata = { // jshint ignore:line
                    "price": vprice,
                    "title": title,
                    "compare_at_price": compare_at_price,
                };

                if (typeof(vars_list[i]) == "string") {
                    vdata["option1"] = vars_list[i];

                    if (product.variants_sku && product.variants_sku.hasOwnProperty(vars_list[i])) {
                        vdata["sku"] = product.variants_sku[vars_list[i]];
                    }
                } else {
                    var sku = [];

                    $.each(vars_list[i], function (j, va) { // jshint ignore:line
                        vdata["option"+(j+1)] = va;

                        if (product.variants_sku && product.variants_sku.hasOwnProperty(va)) {
                            sku.push(product.variants_sku[va]);
                        }
                    });

                    if (sku.length) {
                        vdata["sku"] = sku.join(';');
                    }
                }

                if (product.weight) {
                    vdata.weight = product.weight;
                    vdata.weight_unit = product.weight_unit;
                }
                if (product.combinations && product.combinations.length) {
                    for (var j = 0; j < product.combinations.length; j++) {
                        var variant = product.combinations[j];
                        var match = true;
                        for (var option in variant) {
                            if (variant.hasOwnProperty(option) && option.startsWith('option')) {
                                if (variant[option] != vdata[option]) {
                                    match = false;
                                }
                            }
                        }
                        if (match) {
                            vdata.combination = variant.combination;
                            vdata.quantity = variant.quantity;
                            vdata.price = variant.price;
                            break;
                        }
                    }
                }

                api_data.product.variants.push(vdata);
            }
        } else {
            var data = {
                error: 'Variants should have more than one value separated by comma (,)'
            };

            callback(product, data, callback_data, false);
            return;
        }
    }

    $.ajax({
        url: '/api/shopify',
        type: 'POST',
        data: JSON.stringify ({
            'product': product_id,
            'store': store_id,
            'data': JSON.stringify(api_data),
            'b': true,
        }),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        success: function (data) {
             if (data.hasOwnProperty('id')) {
                taskCallsCount[data.id] = 1;
                waitForTask(data.id, product, data, callback, callback_data);
            } else {
                if (callback) {
                    callback(product, data, callback_data, true);
                }
            }
        },
        error: function (data) {
            if (callback) {
                callback(product, data, callback_data, false);
            }
        }
    });
}

function sendProductToCommerceHQ(productId, storeId, publish, callback) {
    callback = typeof(callback) === 'undefined' ? function() {} : callback;
    var data = {
        product: productId,
        store: storeId,
        publish: publish
    };

    return $.post(api_url('product-export', 'chq'), data, callback);
}

function sendProductToWooCommerce(productId, storeId, publish, callback) {
    callback = typeof(callback) === 'undefined' ? function() {} : callback;
    var data = {
        product: productId,
        store: storeId,
        publish: publish
    };

    return $.post(api_url('product-export', 'woo'), data, callback);
}

function sendProductToEbay(productId, storeId, publish, callback) {
    callback = typeof(callback) === 'undefined' ? function() {} : callback;
    var data = {
        product: productId,
        store: storeId,
        publish: publish
    };

    return $.post(api_url('product-export', 'ebay'), data, callback);
}

function sendProductToFacebook(productId, storeId, publish, callback) {
    callback = typeof(callback) === 'undefined' ? function() {} : callback;
    var data = {
        product: productId,
        store: storeId,
        publish: publish
    };

    return $.post(api_url('product-export', 'fb'), data, callback);
}

function sendProductToGoogle(productId, storeId, publish, callback) {
    callback = typeof(callback) === 'undefined' ? function() {} : callback;
    var data = {
        product: productId,
        store: storeId,
        publish: publish
    };

    return $.post(api_url('product-export', 'google'), data, callback);
}


function sendProductToBigCommerce(productId, storeId, publish, callback) {
    callback = typeof(callback) === 'undefined' ? function() {} : callback;
    var data = {
        product: productId,
        store: storeId,
        publish: publish
    };

    return $.post(api_url('product-export', 'bigcommerce'), data, callback);
}

function sendProductToGearBubble(productId, storeId) {
    var data = {
        product: productId,
        store: storeId,
    };

    return $.post(api_url('product-export', 'gear'), data);
}

function sendProductToGrooveKart(productId, storeId, publish, callback) {
    callback = typeof(callback) === 'undefined' ? function() {} : callback;
    var data = {
        product: productId,
        store: storeId,
        publish: publish
    };

    return $.post(api_url('product-export', 'gkart'), data, callback);
}

function productsEditModal(products) {
    if (!products || !products.length) {
        toastr.warning('No product is selected');
        return;
    }

    var modal = $('#modal-products-edit-form');
    if (isNaN(parseInt(modal.attr('store-id')))) {
        modal.modal('show');
    } else {
        $.ajax({
            url: '/api/product-shopify-id',
            type: 'GET',
            data: {product: products.join(',')},
            success: function (data) {
                if (!data.ids.length) {
                    toastr.warning('Selected products are not found in Shopify');
                    return;
                }
                window.open('/product/edit/connected?' + $.param({
                    store: modal.attr('store-id'),
                    products: data.ids.join(','),
                }), '_blank');
            },
            error: function (data) {
                displayAjaxError('Edit Products');
            }
        });

    }
}

function waitForTask(task_id, product, data, callback, callback_data) {
    taskIntervals[task_id] = setInterval(function () {
        $.ajax({
            url: api_url('export-product'),
            type: 'GET',
            data: {
                id: task_id,
                count: taskCallsCount[task_id]
            },
            context: {
                task_id: task_id,
                product: product,
                data: data,
                callback: callback,
                callback_data: callback_data
            },
            success: function (data) {
                if (data.ready) {
                    clearInterval(taskIntervals[this.task_id]);

                    if (this.callback) {
                        this.callback(this.product, data.data, this.callback_data, true);
                    }
                }
            },
            error: function (data) {
                clearInterval(taskIntervals[this.task_id]);

                if (this.callback) {
                    this.callback(this.product, data.hasOwnProperty('data') ? data.data : data, this.callback_data, false);
                }
            },
            complete: function() {
                taskCallsCount[this.task_id] += 1;
            }
        });
    }, 1000);
}

function setup_full_editor(textarea_name, include_css, editor_variable, custom_tags) {
    include_css = typeof(include_css) !== 'undefined' ? include_css : false;
    editor_variable = typeof(editor_variable) !== 'undefined' ? editor_variable : 'editor';
    custom_tags = typeof(custom_tags) !== 'undefined' ? custom_tags : false;

    var styles = ['body { padding: 15px; }'];
    if (include_css) {
        styles = [
            '//cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.2.0/css/bootstrap.min.css',
            '//cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.2.0/css/bootstrap-theme.min.css',
            '/static/css/main.css',
            'body { padding: 15px; }',
        ];
    }

    if(!CKEDITOR.plugins.registered.hasOwnProperty('customtags')){
        CKEDITOR.plugins.add('customtags', {
        requires: ['richcombo'], //, 'styles' ],
        init: function(editor) {
            var config = editor.config,
                lang = editor.lang.format;

            // Gets the list of tags from the settings.
            var tags = []; //new Array();
            //this.add('value', 'drop_text', 'drop_label');
            tags.push(["{{title}}", "Title", "Title"]);
            tags.push(["{{description_full}}", "Full Description", "Full Description"]);
            tags.push(["{{description_simplified}}", "Simplified Description", "Simplified Description"]);
            tags.push(["{{price}}", "Price", "Price"]);
            tags.push(["{{compare_at_price}}", "Compare At Price", "Compare At Price"]);
            tags.push(["{{weight}}", "Weight", "Weight"]);
            tags.push(["{{vendor}}", "Vendor", "Vendor"]);
            tags.push(["{{type}}", "Type", "Type"]);

            // Create style objects for all defined styles.

            editor.ui.addRichCombo('CustomTags', {
                label: "Custom Tags",
                title: "Custom Tags",
                className: '',
                multiSelect: false,
                panel: {
                    css: ['https://cdnjs.cloudflare.com/ajax/libs/ckeditor/4.5.4/skins/moono/editor.css?t=F969'],
                    voiceLabel: lang.panelVoiceLabel
                },

                init: function() {
                    this.startGroup("Custom Tags");
                    //this.add('value', 'drop_text', 'drop_label');
                    for (var this_tag in tags) {
                        this.add(tags[this_tag][0], tags[this_tag][1], tags[this_tag][2]);
                    }
                },

                onClick: function(value) {
                    editor.focus();
                    editor.fire('saveSnapshot');
                    editor.insertHtml(value);
                    editor.fire('saveSnapshot');
                }
            });
        }
        });
    }

    document[editor_variable] = CKEDITOR.replace(textarea_name, {
        language: 'en',
        contentsCss: styles,
        // Remove unused plugins.
        removePlugins : 'elementspath,dialogadvtab,div,filebrowser,flash,forms,horizontalrule,iframe,liststyle,pagebreak,showborders,stylescombo,templates',
        // Disabled any kind of filtering
        allowedContent : true,
        extraPlugins: (custom_tags ? 'customtags' : ''),
        toolbar :
        [
            { name: 'document', items : [ 'Source','Maximize' ] },
            { name: 'clipboard', items : [ 'Cut','Copy','Paste','PasteText','PasteFromWord','-','Undo','Redo' ] },
            { name: 'editing', items : [ 'Find','Replace','-','SelectAll' ] },
            '/',
            { name: 'basicstyles', items : [ 'Bold','Italic','Underline','Strike','Subscript','Superscript','-','RemoveFormat' ] },
            { name: 'textAlign', items : ['JustifyLeft','JustifyCenter','JustifyRight','JustifyBlock'/*,'-','BidiRtl','BidiLtr'*/ ] },
            { name: 'paragraph', items : [ 'NumberedList','BulletedList','-','Outdent','Indent','-','Blockquote' ] },
            { name: 'insert', items : ['Image', 'Table', 'HorizontalRule', ''] },

            '/',
            { name: 'styles', items : [ 'Format','Font','FontSize' ] },
            { name: 'colors', items : [ 'TextColor','BGColor' ] },
            { name: 'links', items : [ 'Link','Unlink','Anchor', 'SpecialChar', (custom_tags ? 'CustomTags' : '')] },
        ],
    });
}

function setup_admin_editor(textarea_name, include_css, editor_variable) {
    include_css = typeof(include_css) === 'undefined' ? false : include_css;
    editor_variable = typeof(editor_variable) !== 'undefined' ? editor_variable : 'editor';

    var styles = ['body { padding: 15px; }'];
    if (include_css) {
        styles = [
            '//cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.2.0/css/bootstrap.min.css',
            '//cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.2.0/css/bootstrap-theme.min.css',
            '/static/css/main.css',
            'body { padding: 15px; }',
        ];
    }

    document[editor_variable] = CKEDITOR.replace( textarea_name, {
        language: 'en',
        contentsCss: styles,
        allowedContent : true,
    });
}

function editor_sync_content() {
    CKEDITOR.on('instanceReady', function(event) {
        var editor = event.editor;

        editor.on('change', function(event) {
            this.updateElement();
        });
    });
}

function comapre_sku(a, b) {
    try {
        return a.split(/[-:]/).pop().toLowerCase().trim() === b.split(/[-:]/).pop().toLowerCase().trim() ;
    } catch (e) {
        return false;
    }
}

function select_variant(variants, variant_title, variant_sku) {
    // variants: Shopify variants to select
    // variant_title: variant name to test if need to be selected
    // variant_sku: variant SKU to test if need to be selected

    variant_title = variant_title.toLowerCase().trim();
    if (variant_sku) {
        variant_sku = variant_sku.toLowerCase().trim();
    }

    if (typeof(variants) === 'string' && variants.toLowerCase().trim() == variant_title) {
        // Simple variant compare
        return true;
    } else {
        if (typeof(variants) === 'string') {
            if (variants.trim().startsWith('[') && variants.trim().endsWith(']')) {
                variants = JSON.parse(variants);
            } else if (variants.indexOf(',') != -1) {
                // variants is string list of variants separated by ,
                variants = variants.split(',');
            }
        }

        if (typeof(variants) === 'object') {
            for (var i = 0; i < variants.length; i++) {
                var mapped = variants[i];
                if (typeof(mapped) === 'string') {
                    if (mapped.toLowerCase().trim() == variant_title) {
                        return true;
                    }
                } else if (typeof(mapped) === 'object') {
                    if (mapped.sku && variant_sku) {
                        if (comapre_sku(mapped.sku, variant_sku) && (mapped.title.length === 0 || mapped.title.toLowerCase().trim() === variant_title)) {
                            return true;
                        }
                    } else if (mapped.title.toLowerCase().trim() == variant_title) {
                        return true;
                    }
                }
            }
        }
    }

    return false;
}

$(function() {
    $('.icheck').iCheck({
        checkboxClass: 'icheckbox_square-blue',
        radioClass: 'iradio_square-blue',
    });

    var tout = null;
    var showOnMouseEnter = ['#hijacked-warning', '.tos-update'];

    $(showOnMouseEnter[0]).css('top', '-76px').prop('el-top', 77);
    $(showOnMouseEnter.join(',')).mouseenter(function(e) {
        $(this).animate({
            top: "0",
        }, 250);
        if (tout) {
            clearTimeout(tout);
            tout = null;
        }
    }).mouseleave(function(e) {
        var el = this;
        tout = setTimeout(function() {
            var elTop = $(el).prop('el-top') || $(el).outerHeight() - ($(el).outerHeight() / 3);
            $(el).animate({
                top: "-" + elTop + "px",
            }, 300);
        }, 1000);
    });

    function createBoard(e) {
        e.preventDefault();

        var boardName = $('#new-board-add-form [name="title"]').val().trim();
        if (boardName.length === 0) {
            swal('Add Board', 'Board name is required.', 'error');
            return;
        }

        $.ajax({
            url: api_url('boards-add', $('#modal-board-add').attr('store-type')),
            type: 'POST',
            data: {title: boardName},
            success: function(data) {
                if ('status' in data && data.status == 'ok') {
                    $('#modal-board-add').modal('hide');
                    if (typeof(window.onBoardAdd) == 'function') {
                        window.onBoardAdd(data.board);
                    } else {
                        window.location.href = window.location.href.split('#')[0];
                        window.location.reload();
                    }

                    $('#new-board-add-form [name="title"]').val('');
                } else {
                    displayAjaxError('Create Board', data);
                }
            },
            error: function (data) {
                displayAjaxError('Create Board', data);
            }
        });
    }
    $("#new-board-add-form").on('submit', createBoard);
    $('#new-board-add-form [name="title"]').keypress(function (e) {
          if (e.which == 13) {
            createBoard(e);
            return false;
          }
    });
    $('#modal-board-add').on('shown.bs.modal', function() {
        $('#new-board-add-form [name="title"]').trigger('focus');
    });

    $('.add-board-btn').click(function(e) {
        e.preventDefault();
        $('#modal-board-add').modal('show');
    });

    $('.select-all-btn').click(function (e) {
        e.preventDefault();
        var selectStat = ($('.select-all-btn').prop('select-all')===undefined || $(this).prop('select-all') == true);
        ((window.location.href.indexOf('/boards')==-1) ?
            $('input[type="checkbox"]') :
            $(this).parents('.board-box').find('input[type="checkbox"]'))
        .each(function (i, el) {
            $(el).iCheck(selectStat ? 'check' : 'uncheck');
        });

        $(this).prop('select-all', !selectStat);
        $(this).text(!selectStat ? 'Select All' : 'Unselect All');
        document.body.focus();
    });

    $('.paginator-goto').click(function (e) {
        e.preventDefault();

        var url = $(this).attr('data-href');
        if ($(this).prop('input-mode')) {
            return;
        }

        $('span', this).text('').append($('<input>', {
            'style': 'height:25px;width:40px;text-align:center'
        }).keypress(function(e) {
            if (e.which == 13) {
                var inputValue = parseInt($(this).val().trim());
                if (inputValue) {
                    window.location.href = url.replace('paginator-goto', inputValue);
                }

                return false;
            }
        }));

        $(this).prop('input-mode', true);
    });

    $('.unveil').unveil();

    toastr.options.timeOut = 3000;

    Pace.options = {
      ajax: false,
      restartOnRequestAfter: false
    };

    var tooltipOptions = {
        container: 'body'
    };

    if (typeof ($.fn.bootstrapTooltip) === 'undefined') {
        $('.itooltip').tooltip(tooltipOptions);
    } else {
        $('.itooltip').bootstrapTooltip(tooltipOptions);
    }

    $('[qtip-tooltip]').each(function() {
        $(this).qtip({
            content: {
                attr: 'qtip-tooltip',
            },
            position: {
                my: $(this).attr('qtip-my') || "top center",
                at: $(this).attr('qtip-at') ||  "bottom center"
            },
            style: {
                classes: 'qtip-bootstrap'
            },
            hide: {
                 event: 'unfocus',
                 inactive: 3000
             }
        });
    });

    $('a[data-auto-hash]').click(function (e) {
        window.location.hash = $(this).data('auto-hash');
    });

    $('[data-dismissible-id]').click(function (e) {
        e.preventDefault();

        var btn = $(e.currentTarget);

        $.ajax({
            url: api_url('dismissible-view'),
            type: 'POST',
            data: {
                id: btn.data('dismissible-id'),
                hide: true,
            },
        }).always(function() {
            $(btn.data('dismissible-target')).remove();
        });
    });

    $(".side-menu-dropdown").each(function() {
        var collapsedIndex = 0;
        var caretIndex = 1;
        if ($('.sidebar').hasClass('new')) {
            collapsedIndex = 1;
            caretIndex = 2;
        }
        var collapsed = localStorage.getItem($(this.children[0].children[1].children[collapsedIndex]).text());
        if (collapsed === "collapsed") {
            $(this).toggleClass("collapsed");
            this.nextElementSibling.style.display = "none";
            $(this.children[0].children[1].children[caretIndex]).css({"transform": "rotate(180deg)"});
        }
        $(this).on("click", function() {
            $(this).toggleClass("collapsed");
            var dropdownContent = this.nextElementSibling;
            if (!$(this).hasClass("collapsed")) {
                dropdownContent.style.display = "block";
                $(this.children[0].children[1].children[caretIndex]).css({"transform": "none"});
                localStorage.removeItem($(this.children[0].children[1].children[collapsedIndex]).text());
            } else {
                dropdownContent.style.display = "none";
                $(this.children[0].children[1].children[caretIndex]).css({"transform": "rotate(180deg)"});
                localStorage.setItem($(this.children[0].children[1].children[collapsedIndex]).text(), 'collapsed');
            }
        });
    });
});

$('a[data-auto-click]').each(function (i, el) {
    if($(el).data('auto-click') && (
        window.location.hash == '#' + $(el).data('auto-hash') ||
        window.location.hash == $(el).data('auto-click'))) {
        if ($(el).is(':visible')) {
            if ($(el).data('auto-click-onload')) {
                $(function() {
                    $(el).trigger('click');
                });
            } else {
                $(el).trigger('click');
            }
        }
    }
});

$('.dropdown-toggle:not([data-toggle="dropdown"])').on('click', function(e) {
    var dropdownParent = $(this).parent();
    dropdownParent.toggleClass('open');
    if ($(this).data('toggle-id')) {
        var dropdownConfig = sessionStorage.getItem('dropdownConfig') ? JSON.parse(sessionStorage.getItem('dropdownConfig')) : {};
        dropdownConfig[$(this).data('toggle-id')] = dropdownParent.hasClass('open');
        sessionStorage.setItem('dropdownConfig', JSON.stringify(dropdownConfig));
    }
});

var dropdownConfig = sessionStorage.getItem('dropdownConfig') ? JSON.parse(sessionStorage.getItem('dropdownConfig')) : {};
for (var dropdownId in dropdownConfig) {
    $('[data-toggle-id="' + dropdownId + '"]').parent().toggleClass('open', dropdownConfig[dropdownId]);
}

$('img.no-img').on('error', function(e) {
    if($(this).prop('no-img-error') && $(this).prop('no-img-error') > 3) {
        return;
    }

    var img = '//cdn.dropified.com/static/img/' + ($(this).hasClass('no-img-sm') ? 'no-image-sm.png' : 'no-image.png');
    $(this).attr('src', img);

    if ($(this).attr('no-img-width')) {
        $(this).css({
            width: $(this).attr('no-img-width')
        });
    }

    $(this).prop('no-img-error', ($(this).prop('no-img-error') || 0) + 1);
});

function ajustamodal() {
    var altura = $(window).height() - 300; //value corresponding to the modal heading + footer
    $(".ative-scroll").css({
        "height": altura,
        "overflow-y": "auto"
    });
}

$(document).ready(ajustamodal);
$(window).resize(ajustamodal);

(function($) {
    // http://github.com/bgrins/bindWithDelay

    $.fn.bindWithDelay = function(type, data, fn, timeout, throttle) {

        if ($.isFunction(data)) {
            throttle = timeout;
            timeout = fn;
            fn = data;
            data = undefined;
        }

        // Allow delayed function to be removed with fn in unbind function
        fn.guid = fn.guid || ($.guid && $.guid++);

        // Bind each separately so that each element has its own delay
        return this.each(function() {

            var wait = null;

            function cb() {
                var e = $.extend(true, {}, arguments[0]);
                var ctx = this;
                var throttler = function() {
                    wait = null;
                    fn.apply(ctx, [e]);
                };

                if (!throttle) {
                    clearTimeout(wait);
                    wait = null;
                }
                if (!wait) {
                    wait = setTimeout(throttler, timeout);
                }
            }

            cb.guid = fn.guid;

            $(this).bind(type, data, cb);
        });
    };

})(jQuery);

$('.tos-update .close-btn').click(function (e) {
    $.ajax({
        url: '/api/user-config',
        type: 'POST',
        data: {
            'single': true,
            'name': '_tos-update',
            'value': Math.floor(Date.now() / 1000),
        },
        success: function (data) {
            $('.tos-update').remove();
        },
        error: function (data) {
            displayAjaxError('Error', data);
        }
    });
});

$('.dropified-challenge .close-btn').click(function (e) {
    $.ajax({
        url: '/api/user-config',
        type: 'POST',
        data: {
            'single': true,
            'name': '_dropified-challenge',
            'value': Math.floor(Date.now() / 1000),
        },
        success: function (data) {
            $('.dropified-challenge').remove();
        },
        error: function (data) {
            displayAjaxError('Error', data);
        }
    });
});

$('#open-applications-menu').on('click', function(e) {
    e.preventDefault();
    $('#applications-menu').toggleClass('active');
    $('#open-applications-menu').toggleClass('active');
});

$('.dropified-challenge, .dropified-challenge-open').click(function (e) {
    e.preventDefault();

    $.ajax({
        url: '/api/user-config',
        type: 'POST',
        data: {
            'single': true,
            'name': '_dropified-challenge',
            'value': Math.floor(Date.now() / 1000),
        },
        success: function (data) {
            window.location.href = 'https://challenge.dropified.com';
        },
        error: function (data) {
            displayAjaxError('Error', data);
        }
    });
});

$('#download-images').on('click', function(e) {
    e.preventDefault();

    function urlToPromise(url) {
        return new Promise(function(resolve, reject) {
            if (!url.match(/^https:/) || !(url.match(/\.shopify\.com\//) || url.match(/cdn\.dropified\.com/) || url.match(/shopifiedapp-assets/))) {
                url = 'https://app.dropified.com/api/ali/get-image/?' + $.param({url: url});
            }

            JSZipUtils.getBinaryContent(url, function(err, data) {
                if (err) {
                    reject(err);
                } else {
                    resolve(data);
                }
            });
        });
    }

    var zip = new JSZip();
    $.each(product.images, function (i, src) {
        var filename = i + '-' + src.split('/').pop().split('?')[0];

        zip.file(filename, urlToPromise(src), {
            binary: true
        });
    });

    zip.generateAsync({type: 'blob'}).then(function(blob) {
        saveAs(blob, 'product-images-' + config.product_id + '.zip');
    });
});

function versionCompare(left, right) {
    if (typeof left + typeof right != 'stringstring')
        return false;

    var a = left.split('.');
    var b = right.split('.');
    var i = 0,
        len = Math.max(a.length, b.length);

    for (; i < len; i++) {
        if ((a[i] && !b[i] && parseInt(a[i], 10) > 0) || (parseInt(a[i], 10) > parseInt(b[i], 10))) {
            return 1;
        } else if ((b[i] && !a[i] && parseInt(b[i], 10) > 0) || (parseInt(a[i], 10) < parseInt(b[i], 10))) {
            return -1;
        }
    }

    return 0;
}

$('.scrolling-tabs').scrollingTabs({
    disableScrollArrowsOnFullyScrolled: true,
    cssClassLeftArrow: 'fa fa-chevron-left',
    cssClassRightArrow: 'fa fa-chevron-right',
});

$('.find-user-cp').click(function(e) {
    e.preventDefault();

    swal({
        title: $(e.currentTarget).data('title'),
        type: "input",
        showCancelButton: true,
        closeOnConfirm: false,
        animation: "slide-from-top",
        inputPlaceholder: $(e.currentTarget).data('desc'),
        showLoaderOnConfirm: true,
        imageUrl: '//cdn.dropified.com/static/img/person-add.svg',
        imageSize: '120x120',
    }, function(inputValue) {
        if (inputValue === false) return false;
        inputValue = inputValue.trim();
        if (inputValue === "") {
            return false;
        }

        window.location.href = $(e.currentTarget).data('url') + $.param({q: inputValue});
    });
});

$(".copy-text-btn").on("click", function() {
    var text = $(this).attr("data-link");

    navigator.clipboard.writeText(text)
    .then(function(text){
        toastr.info("Registration Link copied");
    })
    .catch(function(err){
        toastr.warning("Unable to copy the Registration link");
    });
});

// this function generates CORB warning, but still track the click and handle cookies
// should be run BEFORE placing an order
function generate_admitad_click(ulp, subid) {
    var helperImg = document.createElement('img');
    helperImg.style.display = 'none';
    helperImg.addEventListener('load', function () {
        document.body.removeChild(helperImg);
    });

    helperImg.addEventListener('error', function () {
        document.body.removeChild(helperImg);
    });

    helperImg.src = 'https://ad.admitad.com/goto/' + window.admitad_site_id + '/?ulp=' + encodeURIComponent(ulp) + '&subid=' + encodeURIComponent(subid);
    document.body.appendChild(helperImg);
}

function sendOrdersToVueApp(btns) {
    if (btns.length) {
        var btn = btns.shift();
        var msg = {
            subject: 'add-order',
            order: {
                'name': btn.attr('order-name'),
                'store': btn.attr('store'),
                'store_type': window.storeType,
                'order_id': btn.attr('order-id'),
                'line_id': btn.attr('line-id'),
                'order_data': JSON.parse(atob(btn.attr('order-data'))),
                'order_store_url': window.location.href,
                'store_name': $('.nav-tabs li.active').text()
            },
        };
        btn.button('loading');
        if (window.admitad_site_id && msg.order.order_data.source_id){
            generate_admitad_click('https://www.aliexpress.com/item/' + msg.order.order_data.source_id + '.html',window.app_base_link);
        }
        $.ajax({
            url: api_url('import-aliexpress-data', 'aliexpress'),
            type: "POST",
            data: JSON.stringify(msg),
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                btn.button('reset');
                msg['order']['shipping_services'] = response.data;
                msg['order']['shipping_setting'] = response.shipping_setting;
                msg['order']['order_data']['variant_price'] = response.price;
                msg['order']['order_data']['sku'] = response.sku;
                msg['order']['order_data']['stock'] = response.stock;
                document.getElementById('orders-aliexpress-frm').contentWindow.postMessage(JSON.stringify(msg), '*');
                sendOrdersToVueApp(btns);

            },
            error: function (response) {
                btn.button('reset');
                msg['order']['shipping_setting'] = '';
                msg['order']['order_data']['variant_price'] = '';
                msg['order']['order_data']['sku'] = '';
                msg['order']['order_data']['stock'] = '';
                document.getElementById('orders-aliexpress-frm').contentWindow.postMessage(JSON.stringify(msg), '*');
                sendOrdersToVueApp(btns);
            },
        });
    }
}

$("#single-click-add-queue").on("click" ,function() {
    var arr = [];
    $(".quick-order-btn").each(function (i, el) {
        var data_target = $(this).attr("data-target");
        if (data_target == "all") {
            var elObj = $(this).closest("div.order");
            elObj.find('.line-checkbox').each(function (i, el) {
                var obj = $(el).closest('div.line');
                var btn= '';
                if ($(obj).hasClass("bundled")) {
                    btn = obj.find('a.quick-bundle-order');
                    btn = $(btn);
                    adddQuickBundleOrders(btn);
                }
                else {
                    btn = obj.find('a.place-order');
                    btn = $(btn);
                    arr.push(btn);
                }
            });
        }
    });
    sendOrdersToVueApp(arr);
});

$(".quick-order-btn").on("click", function(e) {
    e.preventDefault();
    var data_target = $(this).attr("data-target");
    var elObj = $(this).closest("div.order");
    var selected = 0;
    var arr = [];
    elObj.find('.line-checkbox').each(function (i, el) {
        var isChecked = true;
        if (data_target == "selected") {
            isChecked = el.checked;
        }
        if(isChecked) {
            selected += 1;
            var obj = $(el).closest('div.line');
            var btn= '';
            if ($(obj).hasClass("bundled")) {
                btn = obj.find('a.quick-bundle-order');
                btn = $(btn);
                adddQuickBundleOrders(btn);
            }
            else {
                btn = obj.find('a.place-order');
                btn = $(btn);
                arr.push(btn);
            }
        }
    });
    sendOrdersToVueApp(arr);
    if (selected) {
        toastr.success("Items added to Queue");
    } else {
        toastr.warning('Please select an item to add to queue');
    }
});

$('.place-order').on('click', function(e) {
    e.preventDefault();
    var btn = $(e.target);
    sendOrdersToVueApp([btn]);
    toastr.success("Item added to Queue");
});

$('.quick-bundle-order').on("click", function(e) {
    e.preventDefault();
    btn = $(this);
    adddQuickBundleOrders(btn);
});

function adddQuickBundleOrders(btn) {
    var msg = {
        subject: 'add-order',
        order: {
            'name': btn.attr('order-name'),
            'store': btn.attr('store'),
            'store_type': window.storeType,
            'order_id': btn.attr('order-id'),
            'line_id': btn.attr('line-id'),
            'order_data': JSON.parse(atob(btn.attr('order-data')))
        },
    };
    $.ajax({
        url: api_url('import-aliexpress-data-bundle', 'aliexpress'),
        type: "POST",
        data: JSON.stringify(msg),
        dataType: 'json',
        contentType: 'application/json',
        success: function (response) {
            btn.button('reset');
            document.getElementById('orders-aliexpress-frm').contentWindow.postMessage(JSON.stringify(response.data), '*');
            toastr.success("Items added to Queue");
        },
        error: function (response) {
            document.getElementById('orders-aliexpress-frm').contentWindow.postMessage(JSON.stringify(msg), '*');
            toastr.success("Items added to Queue");
        },
    });
}

window.onmessage = function (e) {
    var message;
    var ordersCount = 0;

    try {
        message = JSON.parse(e.data);
    } catch (e) {
        return;
    }

    if (message && message.subject && message.subject == "show-me") {
        if (message.orders) {
            ordersCount = parseInt(message.orders);
        }
        $("#pending-orders-count").text(ordersCount);
    }
};

$.merge(
    $('.hidden-form[data-hidden-link]').map(function() {return $($(this).data('hidden-link'));}),
    $('.hidden-form > a')
).on('click', function(e) {
    e.preventDefault();
    var wrapper = $(this).parent('.hidden-form');
    if (wrapper.hasClass('active')) {
        wrapper.removeClass('active');
    } else {
        wrapper.addClass('active');
        $(document).on('click.hidden-form', function(e) {
            var clickedElem = $(e.target);
            if (wrapper.find('*').index(clickedElem) === -1) {
                wrapper.removeClass('active');
                $(this).off('click.hidden-form');
            }
        });
    }
});

$('[data-click-cookies]').click(function (e) {
    e.preventDefault();
    var elem = $($(this).data('click-elem'));
    console.log('clicked', elem);
    if (!elem.length) {
        return false;
    }
    var cookieName = $(this).data('click-cookies');
    var open = Cookies.get(cookieName) == 'true';
    Cookies.set(cookieName, !open);

    elem.toggleClass('active', !open);
});

function copyLink(e) {
    var plan_url = e.dataset.plan;
    var target_url = window.location.origin + plan_url;
    navigator.clipboard.writeText(target_url)
        .then(function(text){
            toastr.info("Plan Link copied");
        })
        .catch(function(err){
            toastr.warning("Unable to copy the Plan link");
    });
}

$("#bulk-order-close").on("click", function() {
    $(".main-ordering-div").hide("slow");
    $("div#bulk-ordering-app-launcher").show();
});

$("div#bulk-ordering-app-launcher").on("click", function() {
    $(".main-ordering-div").show();
    $(this).hide();
});

$(function() {
    setTimeout(function() {
        var version = $('.extension-version').data('extension-version');
        if (version && window.extensionSendMessage) {
            window.extensionSendMessage({
                subject: 'getVersion',
                from: 'website',
            }, function(rep) {
                if(!rep) {
                    return;
                }

                var current_version = rep.version;
                var comapre = versionCompare(version, current_version);

                if (comapre <= 0) {
                    $('#page-wrapper .footer').removeClass('fixed');
                    $('.extension-version').html('<i class="fa fa-check"></i> Using Latest Extension Version');
                    $('.extension-version').css('color', 'green');
                } else if (comapre > 0) {
                    $('.extension-version').text('New Extension Version Available!');
                    $('.extension-version').append($('<a>', {
                        'class': "btn btn-outline btn-xs btn-success",
                        'href': "/pages/view/how-to-update-the-extension-to-the-latest-version",
                        'style': "margin-left:10px",
                        'html': '<i class="fa fa-refresh" aria-hidden="true"></i> Update',
                    }).click(function(e) {
                        e.preventDefault();

                        $('#page-wrapper .footer').removeClass('fixed');

                        window.extensionSendMessage({
                            subject: 'UpdateExtension',
                            from: 'website',
                        }, function() {
                            $('.extension-version a').hide();
                        });
                    }));

                    $('.extension-version').append($('<a>', {
                        'class': "btn btn-outline btn-xs btn-info",
                        'href': "/pages/extension-changelog",
                        'target': "_blank",
                        'style': "margin-left:10px",
                        'html': '<i class="fa fa-lightbulb-o" aria-hidden="true"></i> What\'s New?',
                    }));

                    if ($('.extension-version').data('required')) {
                        $('#page-wrapper .footer').addClass('fixed');
                    }
                }
            });

        }
    }, 1000);

    if (window.location.hash == '#support' && window.intercomSettings /*&& !window.Intercom*/ ) {
        swal({
            title: 'Dropified Support',
            text: 'It look like our Support App is not loaded correctly, this could be because you are using an <b>Adblocker</b><br>' +
                'Please try to whitelist Dropified website in your adblocking extension.<br>' +
                'You can also contact us by email: <a href="mailto:support@dropified.com">support@dropified.com</a>',
            type: 'warning',
            html: true
        });
    }

    setTimeout(function() {
        if (window.intercomSettings && !window.Intercom) {
            $.ajax({
                url: '/api/user-config',
                type: 'POST',
                data: {
                    single: true,
                    current: true,
                    name: '_adbocler',
                    value: true,
                }
            });
        }
    }, 5000);

    $('#dropdownMenu1, #store-dropdown-menu li').hover(function() {
        $('#store-dropdown-menu').stop(true, true).fadeIn(0);
    }, function() {
        $('#store-dropdown-menu').stop(true, true).delay(200).fadeOut(200);
    });

    $('#store-type-video > *').hover(function() {
        $('#store-type-video > ul').stop(true, true).fadeIn(0);
    }, function() {
        $('#store-type-video > ul').stop(true, true).delay(200).fadeOut(200);
    });
    $('#store-type-video li').click(function(e) {
        $('#store-type-video li.active').removeClass('active');
        $('#selected-video-platform').text($(e.target).text());
        $('#store-type-video > ul').stop(true, true).hide();
    });

    // Select first store platform in list of stores
    var videosStoreType = window.location.pathname.replace(/\//g, '');
    var videosStoreTypeMenu = $('#store-type-video a[href="#' + videosStoreType + '-vids"]');
    if (videosStoreTypeMenu.length === 0) {
        videosStoreType = $('.store-tables tbody tr:first').attr('store-type');
        videosStoreTypeMenu = $('#store-type-video a[href="#' + videosStoreType + '-vids"]');
    }
    if (videosStoreTypeMenu.length === 1 && $('#' + videosStoreType + '-vids .training-video').length >= 0) {
        $('#store-type-video a[href="#' + videosStoreType + '-vids"]').trigger('click');
    }

    if (window.location.href.match(/dropified\.com\/product\?/)) {
        var interval = setInterval(function () {
            var targets = $('#bt_dsers_sync, #getTopObj, .dsers-oberlo-checkoutAll');
            if (!targets.length) {
                clearInterval(interval);
            } else {
                targets.remove();
            }
        }, 1000);
    }

    $.ajaxSetup({
        headers: {'x-frame-size': window.screen.width + '*' + window.screen.height}
    });
});

if (window.intercomSettings) {
    var portalMap = [
        {
            name: 'dashboard',
            selector: '#candu-mount'
        }, {
            name: 'stores-info-above',
            selector: '#candu-stores-info-above'
        }, {
            name: 'saved-products-info-above',
            selector: '#candu-saved-products-info-above'
        }, {
            name: 'boards-info-above',
            selector: '#candu-boards-info-above'
        }, {
            name: 'boards-info-below',
            selector: '#candu-boards-info-below'
        }, {
            name: 'us-products-info-above',
            selector: '#candu-us-products-info-above'
        }, {
            name: 'profit-dashboard-info-above',
            selector: '#candu-profit-dashboard-info-above'
        }, {
            name: 'starter-dashboard',
            selector: '#candu-starter-dashboard'
        }, {
            name: 'bulk-edit',
            selector: '#candu-bulk-edit'
        }, {
            name: 'shopify-migrate',
            selector: '#candu-shopify-migrate'
        }, {
            name: 'dashboard-content',
            selector: '#candu-dashboard-content'
        }, {
            name: 'plod-product-announcements',
            selector: '#candu-plod-product-announcements'
        },
    ];

    portalMap.forEach(function(el) {
        if (window.Candu && document.querySelector(el.selector)) {
            Candu.renderPortal({
                slug: el.name,
                selector: el.selector,
            });
        }
    });
}

var ravenOptions = {
  // Will cause a deprecation warning, but the demise of `ignoreErrors` is still under discussion.
  // See: https://github.com/getsentry/raven-js/issues/73
  ignoreErrors: [
    // Random plugins/extensions
    'top.GLOBALS',
    // See: http://blog.errorception.com/2012/03/tale-of-unfindable-js-error.html
    'originalCreateNotification',
    'canvas.contentDocument',
    'MyApp_RemoveAllHighlights',
    'http://tt.epicplay.com',
    'Can\'t find variable: ZiteReader',
    'jigsaw is not defined',
    'ComboSearch is not defined',
    'http://loading.retry.widdit.com/',
    'atomicFindClose',
    // Facebook borked
    'fb_xd_fragment',
    // ISP "optimizing" proxy - `Cache-Control: no-transform` seems to reduce this. (thanks @acdha)
    // See http://stackoverflow.com/questions/4113268/how-to-stop-javascript-injection-from-vodafone-proxy
    'bmi_SafeAddOnload',
    'EBCallBackMessageReceived',
    // See http://toolbar.conduit.com/Developer/HtmlAndGadget/Methods/JSInjection.aspx
    'conduitPage',
    // Generic error code from errors outside the security sandbox
    // You can delete this if using raven.js > 1.0, which ignores these automatically.
    'Script error.',
    'paintWidget',
    'feathercontrols',
  ],
  ignoreUrls: [
    // Facebook flakiness
    /graph\.facebook\.com/i,
    // Facebook blocked
    /connect\.facebook\.net\/en_US\/all\.js/i,
    // Woopra flakiness
    /eatdifferent\.com\.woopra-ns\.com/i,
    /static\.woopra\.com\/js\/woopra\.js/i,
    // Chrome extensions
    /extensions\//i,
    /^chrome:\/\//i,
    // Other plugins
    /127\.0\.0\.1/i,
    /localhost/i,
    /webappstoolbarba\.texthelp\.com\//i,
    /metrics\.itunes\.apple\.com\.edgesuite\.net\//i,
    // AViary Image Editor
    /feather\.aviary\.com/i,
    // CDNJS
    /cdn\/js\//,
    /ajax\/libs\//,
    /frame.[^\.]{8}.js/,
  ]
};

if (typeof currentUser !== 'undefined') {
    var raven = Raven.config('//9449f975eb984492bc9205e5acd0f36a@sentry.io/73544', ravenOptions);
    raven.install();
    raven.setUserContext(currentUser);
}

function unsecuredCopyToClipboard(text) {
    var $txt = $('<textarea />');
    $txt.val(text).css({ width: "1px", height: "1px" }).appendTo('body');
    $txt.select();
    try {
        document.execCommand('copy');
        toastr.success('Copying to clipboard was successful!', 'Copy to Clipboard');
    } catch(err) {
        toastr.error('Could not copy text.', 'Copy to Clipboard');
    }
    $txt.remove();
}

function copyToClipboard(text) {
    if (window.isSecureContext && navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function () {
            toastr.success('Copying to clipboard was successful!', 'Copy to Clipboard');
        }, function (err) {
            toastr.error('Could not copy text.', 'Copy to Clipboard');
        });
    } else {
        unsecuredCopyToClipboard(text);
    }
}

function copyToClipboardPermissionWrapper(text) {
    if (window.isSecureContext && navigator.permissions && navigator.permissions.query) {
        navigator.permissions.query({name: "clipboard-write"}).then(function(result) {
            if (result.state === "granted" || result.state === "prompt") {
                copyToClipboard(text);
            }
        });
    } else {
        unsecuredCopyToClipboard(text);
    }
}
