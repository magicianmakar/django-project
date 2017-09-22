// 'use strict';
/* global $, toastr, swal, CKEDITOR */

var taskIntervals = {};
var taskCallsCount = {};

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

function displayAjaxError(desc, data) {
    var error_msg = 'Server error.';

    if (typeof (data.error) == 'string') {
        error_msg = data.error;
    } else if (data.responseJSON && typeof (data.responseJSON.error) == 'string') {
        error_msg = data.responseJSON.error;
    } else if (typeof (data) == 'string') {
        error_msg = data;
    }

    swal(desc, error_msg, 'error');
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

        if (vars_list.length>0) {
            vars_list = allPossibleCases(vars_list);

            for (var i=0; i<vars_list.length; i++) {
                var title = vars_list[i].join ? vars_list[i].join(' & ') : vars_list[i];

                var vdata = {
                    "price": product.price,
                    "title": title,
                };

                if (typeof(vars_list[i]) == "string") {
                    vdata["option1"] = vars_list[i];

                    if (product.variants_sku && product.variants_sku.hasOwnProperty(vars_list[i])) {
                        vdata["sku"] = product.variants_sku[vars_list[i]];
                    }
                } else {
                    var sku = [];

                    $.each(vars_list[i], function (j, va) {
                        vdata["option"+(j+1)] = va;

                        if (product.variants_sku && product.variants_sku.hasOwnProperty(va)) {
                            sku.push(product.variants_sku[va]);
                        }
                    });

                    if (sku.length) {
                        vdata["sku"] = sku.join(';');
                    }
                }

                if (product.compare_at_price) {
                    vdata.compare_at_price = product.compare_at_price;
                }

                if (product.weight) {
                    vdata.weight = product.weight;
                    vdata.weight_unit = product.weight_unit;
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

function sendProductToCommerceHQ(productId, storeId, publish) {
    var data = {
        product: productId,
        store: storeId,
        publish: publish
    };

    return $.post(api_url('product-export', 'chq'), data);
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

$(function() {
    $('.icheck').iCheck({
        checkboxClass: 'icheckbox_square-blue',
        radioClass: 'iradio_square-blue',
    });

    $(".add-board-btn").click(function(e) {
        e.preventDefault();
        $('#modal-board-add').modal('show');
    });

    var tout = null;
    var showOnMouseEnter = ['#hijacked-warning', '.tos-update'];

    $(showOnMouseEnter[0]).css('top', '-35px').prop('el-top', 36);
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
            var elTop = $(el).prop('el-top') || $(el).outerHeight() - (($(el).outerHeight() / 3) * 1);
            $(el).animate({
                top: "-" + elTop + "px",
            }, 300);
        }, 1000);
    });

    function createBoard(e) {
        e.preventDefault();

        var board_name = $('#add-board-name').val().trim();
        if (board_name.length === 0) {
            swal('Add Board', 'Board name is required.', 'error');
            return;
        }

        $.ajax({
            url: api_url('boards-add', $('#modal-board-add').prop('store-type')),
            type: 'POST',
            data: {
                title: board_name
            },
            success: function(data) {
                if ('status' in data && data.status == 'ok') {
                    $('#modal-board-add').modal('hide');
                    if (typeof(window.onBoardAdd) == 'function') {
                        window.onBoardAdd(data.board);
                    } else {
                        window.location.href = window.location.href;
                    }

                    $('#add-board-name').val('');
                } else {
                    displayAjaxError('Create Board', data);
                }
            },
            error: function (data) {
                displayAjaxError('Create Board', data);
            }
        });
    }

    $("#new-board-add-form").submit(createBoard);
    $("#board-add-send").click(createBoard);
    $("#board-add-send").keypress(function (e) {
          if (e.which == 13) {
            createBoard(e);
            return false;
          }
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
});

$('a[data-auto-click]').each(function () {
    if($(this).data('auto-click') && (
        window.location.hash == '#' + $(this).data('auto-hash') ||
        window.location.hash == $(this).data('auto-click'))) {
        $(this).trigger('click');
    }
});

$('img.no-img').on('error', function(e) {
    if($(this).prop('no-img-error') && $(this).prop('no-img-error') > 3) {
        return;
    }

    var img = '//d2kadg5e284yn4.cloudfront.net/static/img/' + ($(this).hasClass('no-img-sm') ? 'no-image-sm.png' : 'no-image.png');
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
            text: 'It look like our Support App is not loaded correctly, this could be because you are using and <b>Adblocker</b><br>' +
                'Please try to whitelist Dropified website in your adblocking extension.<br>' +
                'You can also contact use by email: <a href="mailto:support@dropified.com">support@dropified.com</a>',
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


    $('[data-toggle="dropdown"]').click(function (e) {
        setTimeout(function () {
            if (!$(e.target).parent().hasClass('open')) {
                $(e.target).trigger('click');

                if(!window.workaroundCaptured) {
                    Raven.captureMessage('Dropdown Workaround');
                    window.workaroundCaptured = true;
                }
            }
        }, 200);
    });
});

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
