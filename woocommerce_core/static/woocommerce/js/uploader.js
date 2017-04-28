/* global $, config, toastr, product */

(function(config, product) {
'use strict';

$('#modal-upload-image').on('show.bs.modal', function (e) {
    $('.upload-image-btn').bootstrapBtn('reset');
    $('#file_input').prop('value', '');
});

$('.upload-image-btn').click(function (e) {
    var files = document.getElementById("file_input").files;
    var file = files[0];
    if(file == null){
        alert("No file selected.");
    } else {
        $(this).bootstrapBtn('loading');
        get_signed_request(file);
    }
});

function get_signed_request(file){
    var xhr = new XMLHttpRequest();
    xhr.open("GET", "/upload/sign_s3?file_name=uploads/u"+config.user_id+"/"+file.name+"&file_type="+file.type);
    xhr.onreadystatechange = function(){
        if(xhr.readyState === 4) {
            if(xhr.status === 200) {
                var response = JSON.parse(xhr.responseText);
                if ('error' in response && typeof(response.error)=='string') {
                    alert('Upload error: '+response.error);
                } else {
                    upload_file(file, response.signed_request, response.url);
                }
            } else {
                alert("Could not get signed URL.");
            }

            $('.upload-image-btn').bootstrapBtn('reset');
        }
    };
    xhr.send();
}

function upload_file(file, signed_request, url){
    var xhr = new XMLHttpRequest();
    xhr.open("PUT", signed_request);
    xhr.setRequestHeader('x-amz-acl', 'public-read');
    xhr.onload = function() {
        if (xhr.status === 200) {
            file_uploaded(url);
        }
    };
    xhr.onerror = function() {
        alert("Could not upload file.");
    };
    xhr.send(file);
}

function file_uploaded(url) {
    product.images.push(url);
    document.renderImages();
    /*
    $.ajax({
        type: 'POST',
        url: '/api/add-user-upload',
        data: {
            'url': url,
            'product': config.product_id,
        },
        success: function(data) {},
        error: function(data) {},
    });
    */
}

document.file_uploaded = file_uploaded;
})(config, product);
