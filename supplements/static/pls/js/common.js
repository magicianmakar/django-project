$(document).ready(function(){
    $('.custom-file-input').on('change', function() {
        var fileName = $(this).val().split('\\').pop();
        var nextLabel = $(this).next('.custom-file-label');

        if (fileName !== '') {
          nextLabel.addClass("selected").html(fileName);
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

    $(".download-label").click(function () {
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
    });

    $(".add-loader").click(function () {
        $(this).button('loading');
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
                toastr.success("Successfully marked elected lines as printed.");
            }
        });
    });

    $("#select-all-lines").click(function () {
        $('.line-checkbox').prop('checked', $(this).prop('checked'));
    });

    $("#id_shipping_countries").chosen();
});
