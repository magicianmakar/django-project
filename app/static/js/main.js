// 'use strict';
/* global $, toastr, swal, CKEDITOR */

var taskIntervals = {};
var taskCallsCount = {};

function allPossibleCases(arr) {
  if (arr.length == 1) {
    return arr[0];
  } else {
    var result = [];
    var allCasesOfRest = allPossibleCases(arr.slice(1));  // recur with the rest of array
    for (var i = 0; i < allCasesOfRest.length; i++) {
      for (var j = 0; j < arr[0].length; j++) {
        result.push([arr[0][j], allCasesOfRest[i]]);
      }
    }
    return result;
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

function hashUrlFileName(s) {
    var url = cleanUrlPatch(s);
    var ext = getFileExt(s);

    var hash = 0, i, chr, len;
    if (url.length === 0) return hash;
    for (i = 0, len = url.length; i < len; i++) {
        chr = url.charCodeAt(i);
        hash = ((hash << 5) - hash) + chr;
        hash |= 0; // Convert to 32bit integer
    }
    return hash + '.' + ext;
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
        "vendor": "",
        "published": false,
        "tags": product.tags,
        "variants": [],
        "options": [],
        "images" :[]
      }
    };

    if (product.images) {
        for (var i=0; i<product.images.length; i++) {
            api_data.product.images.push({
                src: product.images[i]
            });
        }
    }

    if (typeof(product.weight) !== 'number') {
        product.weight = 0.0;
    }

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
            if (el.values.length>1) {
                api_data.product.options.push({
                    'name': el.title,
                    'values': el.values
                });
            }
        });

        var vars_list = [];
        $(product.variants).each(function (i, el) {
            if (el.values.length>1) {
                vars_list.push(el.values);
            }
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
                } else {
                    $.each(vars_list[i], function (j, va) {
                        vdata["option"+(j+1)] = va;
                    });
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
                window.open(modal.attr('store-url') + '/admin/bulk?' + $.param({
                    "resource_name": "Product",
                    "return_toh": "/admin/products",
                    "routing_method": "shop_from_host",
                    "protocol": "https://",
                    "edit": "variants.price,variants.compare_at_price,product_type,variants.weight,title",
                    "show": "",
                    "ids": data.ids.join(','),
                    "metafield_titles": "",
                    "metafield_options": "",
                    "SA": "true",
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
            url: '/api/export-product',
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

function setup_full_editor(textarea_name, include_css) {
    include_css = typeof(include_css) === undefined ? false : include_css;

    var styles = ['body { padding: 15px; }'];
    if (include_css) {
        styles = [
            '//cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.2.0/css/bootstrap.min.css',
            '//cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.2.0/css/bootstrap-theme.min.css',
            '/static/css/main.css',
            'body { padding: 15px; }',
        ];
    }

    document.editor = CKEDITOR.replace( textarea_name,
    {
        contentsCss: styles,
        // Remove unused plugins.
        removePlugins : 'elementspath,dialogadvtab,div,filebrowser,flash,forms,horizontalrule,iframe,liststyle,pagebreak,showborders,stylescombo,templates',
        // Disabled any kind of filtering
        allowedContent : true,
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
            { name: 'links', items : [ 'Link','Unlink','Anchor', 'SpecialChar' ] },
        ],
    });
}

function setup_admin_editor(textarea_name, include_css) {
    include_css = typeof(include_css) === undefined ? false : include_css;

    var styles = ['body { padding: 15px; }'];
    if (include_css) {
        styles = [
            '//cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.2.0/css/bootstrap.min.css',
            '//cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.2.0/css/bootstrap-theme.min.css',
            '/static/css/main.css',
            'body { padding: 15px; }',
        ];
    }

    document.editor = CKEDITOR.replace( textarea_name, {
        contentsCss: styles,
        allowedContent : true,
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
    $('#hijacked-warning').css('top', '-35px');
    $('#hijacked-warning').mouseenter(function (e) {
        $( this ).animate({
            top: "0",
        }, 500, function() {
            // Animation complete.
        });
        if (tout) {
            clearTimeout(tout);
            tout = null;
        }
    }).mouseleave(function (e) {
        // $(this).css('top', '-22px');
        var el = this;
        tout = setTimeout(function() {
            $( el ).animate({
                top: "-35px",
            }, 500, function() {
                // Animation complete.
            });
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
            url: '/api/boards-add',
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

    $('.itooltip').tooltip();

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
            }
        });
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
    'Script error.'
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
  ]
};

var raven = Raven.config('//9449f975eb984492bc9205e5acd0f36a@app.getsentry.com/73544', ravenOptions);
raven.install();

if (typeof currentUser !== 'undefined') {
    raven.setUserContext(currentUser);
}
