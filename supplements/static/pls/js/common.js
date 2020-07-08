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

    $('.delete-product-btn').click(function(e) {
        var btn = $(this);
        var product = btn.parents('.product-box').attr('product-id');
        var data = {'product': product};

        swal({
                title: "Delete Supplement",
                text: "Are you sure you want to delete this supplement?",
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
                            window.location.reload();
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

    $('.make-refund').click(function (e) {
        var orderId = $(this).data('order-id');
        var form = document.getElementById('refund_form');
        form.order_id.value = orderId;
    });

    $("#id_shipping_countries").chosen();
    $("#id_label_size_filter").chosen();
    $("#id_product_sku_filter").chosen();
    $('#id_label_sku_filter').chosen();
    $('#id_product_supplement_sku').chosen();
});
