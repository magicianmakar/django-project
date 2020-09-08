$(window.plupload_Config.saveFormID).on("addmockups", function(e, url) {
    e.preventDefault();
    $('#mockup-thumbnails').append($('<img>').attr('src', url));
}).on("cleanmockups", function(e) {
    e.preventDefault();
    $('#mockup-thumbnails').empty();
}).on("addlabel", function(e) {
    e.preventDefault();
    var fileList = $('#label').get(0).files;
    if (fileList.length > 0) {
        $('#single-label-upload').get(0).files = fileList;
    }
});

$('#single-label-upload').on('change', function() {
    // Update label in mockup editor
    var files = this.files;
    var reader = new FileReader();
    reader.onload = function() {
        if (!this.result.includes('application/pdf')) {
            swal("Only PDF Formatted Label allowed");
            return;
        }

        var pdf = this.result;
        var defaultSize = $('#id_label_size').val();
        labelSizeMatch(defaultSize, pdf).then(function (result) {
            addLabelImage(pdf);
            $('#label').get(0).files = files;

            // Update generated mockups and show progress
            var progress = $('<div class="progress mockup-save-progress">');
            $('#mockup-thumbnails').empty().after(progress);
            $('[name="mockup_urls"]').remove();
            mockupsUploader.addFile(files[0]);
            mockupsUploader.start();

            $(window.plupload_Config.saveFormID).on("addlabel", function(e) {
                e.preventDefault();
                $(this).off(e);
                progress.remove();
            });
        }).catch(function (error){
            swal(
                "Label size does not match",
                "The PDF uploaded does not match the required label size i.e. " + defaultSize,
                "warning"
            );
            return;
        });
    };
    reader.readAsDataURL(this.files[0]);
});

$("#id_comment").attr("placeholder", "Leave a comment...");
$("input[name='is_private']").change(function() {
    $("#id_comment").toggleClass('bg-private', $(this).is(":checked"));
    if($(this).is(":checked")) {
        $("#id_comment").attr("placeholder", "Leave a private note...");
    } else {
        $("#id_comment").attr("placeholder", "Leave a comment...");
    }
});
