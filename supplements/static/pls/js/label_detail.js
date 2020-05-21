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
    var reader = new FileReader();
    reader.onload = function() {
        if (!this.result.includes('application/pdf')) {
            swal("Only PDF Formatted Label allowed");
            return;
        }

        addLabelImage(this.result);
    };
    reader.readAsDataURL(this.files[0]);
    $('#label').get(0).files = this.files;

    // Update generated mockups and show progress
    var progress = $('<div class="progress mockup-save-progress">');
    $('#mockup-thumbnails').empty().after(progress);
    $('[name="mockup_urls"]').remove();
    mockupsUploader.addFile(this.files[0]);
    mockupsUploader.start();

    $(window.plupload_Config.saveFormID).on("addlabel", function(e) {
        e.preventDefault();
        $(this).off(e);
        progress.remove();
    });
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
