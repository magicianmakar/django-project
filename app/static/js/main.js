
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

function sendProductToShopify (product, store_id, product_id, callback, callback_data) {
    if (!store_id || store_id.length==0) {
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
            })
        }
    }

    if (product.variants.length==0) {
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
            // alert('Variants should have more than one value separated by comma (,)');
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
        }),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        success: function (data) {
            if (callback) {
                callback(product, data, callback_data, true);
            }
        },
        error: function (data) {
            if (callback) {
                callback(product, data, callback_data, false);
            }
        }
    });
};