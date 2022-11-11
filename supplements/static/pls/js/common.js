function markLabelAsPrinted() {
    var item = $(this).data('item-id');
    var url = api_url('mark-printed', 'supplements');
    data = {'item-id': item};
    $.ajax({
        url: url,
        type: "POST",
        data: JSON.stringify(data),
        dataType: 'json',
        contentType: 'application/json',
    });
}

$(document).ready(function(){
    $('.custom-file-input').on('change', function() {
        var fileName = $(this).val().split('\\').pop();
        var nextLabel = $(this).next('.custom-file-label');

        if (fileName !== '') {
          nextLabel.addClass("selected").html(fileName.substring(0, 27));
        } else {
          nextLabel.html(nextLabel.data('placeholder'));
        }
    });

    $("input[type='reset']").closest('form').on('reset', function() {
        $('.custom-file-label').each(function (i, el) {
            $(el).html($(el).data('placeholder'));
        });

        var commentField = CKEDITOR.instances['id_comment'];
        if (commentField) {
            commentField.setData('');
        }
    });

    $(".pls-reset-btn").click(function () {
        $(".form-control").each(function (i, item) {
            $(item).val('');
        });
    });

    $(".download-label").click(markLabelAsPrinted);

    $(".add-loader").click(function () {
        if ($(this).parents('form')[0].checkValidity()) {
            $(this).button('loading');
        }
    });

    $(".paging-supplement .dropdown-menu a").click(function(event){
        var paginateBy = parseInt($(this).text());
        var finalString = '';
        var url = new URL(window.location.toString());
        var searchParams = new URLSearchParams(url.search);

        if (!searchParams.has('paginate_by') && paginateBy == 20) {
            toastr.info("Already showing " + paginateBy + " items a page");
            return false; // 20 Items a page are shown by default
        }
        if (window.location.search !== '') {
            if (searchParams.has('paginate_by')) {
                if (parseInt(searchParams.get('paginate_by')) == paginateBy) {
                    toastr.info("Already showing " + paginateBy + " items a page");
                    return false; // Do not redirect if User choose same number to paginate by
                }
                searchParams.delete('paginate_by');
            }
            if (searchParams.has('page')) {
                searchParams.delete('page'); // Start from page 1 when total items in a page change
            }
            searchParams.forEach(function(value, key) {
                searchParams.set(key, value); // set function ensures that query string param key doesn't repeat.
            });
            finalString = searchParams.toString();
        }
        window.location.href = "?" + finalString + "&paginate_by=" + paginateBy;
    });

    $('#dropdownMenu2, #store-dropdown-menu-2 li').hover(function() {
        $('#store-dropdown-menu-2').stop(true, true).fadeIn(0);
    }, function() {
        $('#store-dropdown-menu-2').stop(true, true).delay(200).fadeOut(200);
    });

    $("#print-all-labels").click(function (e) {
        e.preventDefault();
        var data = {'item-ids': []};
        $(".line-checkbox").each(function (i, item) {
            if ($(item).prop('checked')) {
                data['item-ids'].push($(item).data("id"));
            }
        });
        if (data['item-ids'].length === 0) {
            toastr.info("Please select line items to print labels against.");
            return;
        }

        $("#print-message").html("Processing...");
        var url = api_url('bulk-print', 'supplements');
        $.ajax({
            url: url,
            type: "POST",
            data: JSON.stringify(data),
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                var url = response['download-url'];
                var link = "<a href='" + url + "' target='_blank'>Download All</a>";
                $("#print-message").html(link);
            }
        });
    });

    $("#mark-all-labels").click(function (e) {
        e.preventDefault();
        var data = {'item-ids': []};
        $(".line-checkbox").each(function (i, item) {
            if ($(item).prop('checked')) {
                data['item-ids'].push($(item).data("id"));
            }
        });
        if (data['item-ids'].length === 0) {
            toastr.info("Please select line items to mark labels against.");
            return;
        }

        var url = api_url('bulk-mark', 'supplements');
        $.ajax({
            url: url,
            type: "POST",
            data: JSON.stringify(data),
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                toastr.success("Successfully marked selected lines as printed.");
                window.location.href = window.location.href;
            }
        });
    });

    $("#unmark-all-labels").click(function (e) {
        e.preventDefault();
        var data = {'item-ids': []};
        $(".line-checkbox").each(function (i, item) {
            if ($(item).prop('checked')) {
                data['item-ids'].push($(item).data("id"));
            }
        });
        if (data['item-ids'].length === 0) {
            toastr.info("Please select line items to unmark labels against.");
            return;
        }

        var url = api_url('bulk-unmark', 'supplements');
        $.ajax({
            url: url,
            type: "POST",
            data: JSON.stringify(data),
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                toastr.success("Successfully marked selected lines as not printed.");
                window.location.href = window.location.href;
            }
        });
    });

    $("#select-all-lines").click(function () {
        $('.line-checkbox').prop('checked', $(this).prop('checked'));
    });

    $('.delete-pls-btn').click(function(e) {
        var btn = $(this);
        var product_id = btn.parents('.product-box').attr('product-id');
        if (typeof(product_id) === 'undefined') {
            product_id = new URL(window.location.href).pathname.split('/').filter(Boolean).pop();
        }
        var data = {'product': product_id};
        swal({
                title: "Delete Supplement",
                text: "Are you sure you want to delete this supplement?\nDoing so will also delete your labels",
                type: "warning",
                showCancelButton: true,
                closeOnConfirm: false,
                showLoaderOnConfirm: true,
                confirmButtonColor: "#DD6B55",
                confirmButtonText: "Delete",
                cancelButtonText: "Cancel"
            },
            function(isConfirmed) {
                if (isConfirmed) {
                    $.ajax({
                        url: api_url('delete_usersupplement', 'supplements'),
                        type: 'POST',
                        data: data,
                        success: function(data) {
                            swal.close();
                            toastr.success("The Supplement has been deleted.", "Deleted!");
                            window.location.href = '/supplements/my/supplement/list';
                        },
                        error: function(data) {
                            displayAjaxError('Delete Supplement', data);
                        }
                    });
                }
            }
        );
    });

    $('.generate-payment-pdf').click(function (e) {
        e.preventDefault();
        var url = $(this).attr('href');
        userHasBilling().then(function (result) {
            window.open(url, '_blank');
        }).catch(function (error){
            return;
        });
    });

    $('.make-refund').click(function (e) {
        var orderId = $(this).data('order-id');
        $.ajax({
            url: api_url('order-lines', 'supplements'),
            type: 'GET',
            data: {order_id: orderId},
            success: function(data) {
                var form = document.getElementById('refund_form');
                form.order_id.value = orderId;
                var addLinesTemplate = Handlebars.compile($("#id-add-line-items-template").html());
                Handlebars.registerHelper('ifeq', function (a, b, options) {
                    if (a == b) { return options.fn(this); }
                    return options.inverse(this);
                });
                var html = addLinesTemplate(data);
                $('#modal-orders-refund tbody').empty().append(html);
                $('#modal-orders-refund').modal('show');
                $('#shipping_price').empty().text(data.shipping_price_string);
                $('#shipping_price').attr("data-shipping-price", data.shipping_price);
                $('#id_shipping').val("");
                $('#id_fee').val("");
                $('#total_refund').val("");
                if (data.transaction_status == "capturedPendingSettlement"){
                    $('#id_shipping').prop('readonly', true);
                    $('#id_shipping').val(data.shipping_price);
                    $('#id_fee').prop('readonly', true);
                    $('#total_refund').val(data.amount);
                    $('#void_warning').show();
                } else {
                    $('#id_shipping').prop('readonly', false);
                    $('#id_fee').prop('readonly', false);
                    $('#void_warning').hide();
                }
            }
        });
    });

    $('#add-refund').click(function (e) {
        var form = document.getElementById('refund_form');
        var amount = 0;
        var data = {};
        var fee = $("#id_fee").val();
        var shipping = $("#id_shipping").val();
        if (form.checkValidity()) {
            $(".refund-amount").each(function (i, item) {
                if ($(item).val()) {
                    data[($(item).data("line-id"))] = $(item).val();
                    amount += parseFloat($(item).val());
                }
            });
        }
        form.fee.value = fee ? fee : 0;
        form.shipping.value = shipping ? shipping : 0;
        form.amount.value = amount;
        form.line_items_data.value = JSON.stringify(data);
    });

    $('#id_fee').change(function() {
        calculate_total_refund();
    });

    $('#id_shipping').change(function() {
        calculate_total_refund();
    });

    $('.mark-supplement').click(function (e) {
        e.preventDefault();
        var item = $(this).data('item-id');
        var data = {'item_id': item};

        $.ajax({
            url: api_url('mark-usersupplement-unread', 'supplements'),
            type: "POST",
            data: JSON.stringify(data),
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                toastr.success("The supplement has been successfully marked unread.", "Success!");
            }
        });
    });

    $(".check-supplier input[type='checkbox']").click(function (e) {
        var input = $(this).parents('.check-supplier').find('input[type="text"]');
        if ($(this).prop('checked')) {
            $(input).attr('placeholder', 'Add reference number');
            $(input).prop('disabled', false);
        } else {
            $(input).attr('placeholder', '');
            $(input).prop('disabled', true);
            $(input).val('');
        }
    });

    $("#create-payouts").click(function (e) {
        e.preventDefault();
        var data = {};
        $(".check-supplier input[type='checkbox']").each(function (i, item) {
            var id = $(item).attr('id');
            var input = $(item).parents('.check-supplier').find('input[type="text"]');
            var date = $(item).parents('.check-supplier').find('input[type="hidden"]');
            if ($(item).prop('checked')) {
                data[id] = {
                    'ref_num': $(input).val(),
                    'date': $(date).val(),
                };
            }
        });
        if (Object.keys(data).length == 0) {
            toastr.info("Please select at least one supplier to add payouts.");
            return;
        }
        for (var id in data) {
            if (!data[id].ref_num) {
                toastr.info('Please make sure to enter reference number for each selected supplier.');
                return;
            }
        }

        $.ajax({
            url: api_url('create-payouts', 'supplements'),
            type: "POST",
            data: JSON.stringify(data),
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                if (response.count == 0) {
                    toastr.info('There were no orders found to add in payout hence, No Payout Added.');
                    return;
                }
                toastr.success("Payout was created successfully.", "Success!");
                window.location.reload();
            }
        });
    });

    $("#id_shipping_countries").chosen();
    $("#id_label_size_filter").chosen();
    $("#id_product_sku_filter").chosen();
    $('#id_label_sku_filter').chosen();
    $('#id_product_supplement_sku').chosen();
});
