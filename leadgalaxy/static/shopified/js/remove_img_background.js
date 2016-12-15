(function(config, product) {

    'use strict';
    $( document ).on( 'click', '.var-image-block .remove-background-image-editor', function(e) {
        e.preventDefault();

        var all_ok = true;
        var image = $( this ).siblings( 'img' );
        if ( config.clipping_magic.clippingmagic_editor && config.clipping_magic.stripe_customer) {
            if ( !$.trim( config.clipping_magic.api_id ).length || !$.trim( config.clipping_magic.api_secret ).length ) {
                $('#modal-clippingmagic').modal('show');
                all_ok = false;
            }
        } else {
            swal('Error', 'You haven\'t subscribe for this feature.', 'error');
            all_ok = false;
        }

        if ( all_ok ) {
            $.post( '/api/edit-image', {
                api_id: config.clipping_magic.api_id,
                api_secret: config.clipping_magic.api_secret,
                image_url: image.attr( 'src' ),
                product_id: config.product_id,
                action: 'edit',
            })
            .done( function( data ) {
                if ( data.status == 'OK' ) {
                    edit_image( data, image )
                } else {
                    swal( {
                        title: "Error",
                        text: data.msg,
                        type: "error",
                        html: true,
                        closeOnConfirm: true,
                        animation: false,
                        confirmButtonText: "Ok"
                    } );
                }
            })
            .fail(function(e){
                swal('Error', 'Something went wrong.', 'error');
            });
        }
    });

    $('#save-clippingmagic').click(function () {
        var all_ok = true;
        if(!$.trim( $( ".api_id", $( '#modal-clippingmagic' ) ).val() ).length ||
		   !$.trim( $( ".api_key", $( '#modal-clippingmagic' ) ).val() ).length ) {
            all_ok = false;
            swal('Error', 'Please enter required fields.', 'error');
        }

        if( all_ok ) {
		var btn = $(this);
		btn.bootstrapBtn('loading');

		$.ajax({
		    url: '/api/user-clippingmagic',
		    type: 'POST',
		    data: $('form#user-clippingmagic').serialize(),
		    context: {btn: btn},
		    success: function (data) {
		        if ( data.reload ) {
		            $('#modal-clippingmagic').modal('hide');
		            window.location.reload();
		        } else {
		            swal('Error', 'Something went wrong.', 'error');
		        }
		    },
		    error: function (data) {
		        swal('Error', 'Something went wrong.', 'error');
		    },
		    complete: function () {
		        this.btn.bootstrapBtn('reset');
		    }
		});
        }
    });

    function edit_image( data, image ) {
        try{
            var errorsArray = ClippingMagic.initialize({apiId: parseInt( data.api_id )});
            if ( errorsArray.length > 0 )
                swal('Error', "Sorry, your browser is missing some required features: \n\n " + errorsArray.join("\n "), 'error');

            image.siblings(".loader").show();
            ClippingMagic.edit( {"image" : {"id" : parseInt( data.image_id ), "secret" : data.image_secret}, "locale" : "en-US"}, function( response ) {
                if( response.event == 'result-generated' ) {
                    $.post('/api/edit-image',{
                        api_id: config.clipping_magic.api_id,
                        api_secret: config.clipping_magic.api_secret,
                        image_id: response.image.id,
                        product: config.product_id,
                        action: 'done',
                    })
                    .done( function( data ) {
                        $.post('/upload/save_image_s3',{
                            product: config.product_id,
                            url: data.image_url,
                            clippingmagic: config.clipping_magic.clippingmagic_editor,
                        })
                        .done( function( data ) {
                            image.attr( 'src', data.url ).siblings(".loader").hide();
                            product.images[parseInt(image.attr('image-id'), 10)] = data.url;
                            toastr.info('Please click "Save for Later" or "Update to Shopify" to apply changes. If still unsaved, you may lose your credit point.','Alert');
                            toastr.options = { "showDuration": "10000", "hideDuration": "10000", "timeOut": "10000", "extendedTimeOut": "10000" }
                        })
		        .fail( function( e ) {
			    swal('Error', 'Something went wrong.', 'error');
		        });
                    })
                    .fail(function(e){
                        swal('Error', 'Something went wrong.', 'error');
                    });
                } else {
                    image.siblings(".loader").hide();
                    swal('Error', response.error.message, 'error');
                }
            });
        } catch ( e ) {
            swal('Error', e, 'error');
        }
    }

})(config, product);