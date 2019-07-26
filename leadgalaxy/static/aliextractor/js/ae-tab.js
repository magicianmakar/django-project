(function() {
'use strict';

$('.ae-extension-check, .ae-modal-extension-check').show();
$('.ae-extension-content, .ae-modal-extension-content').hide();

setTimeout(function() {

        if (window.AE_extensionSendMessage) {

            window.AE_extensionSendMessage({
                method: 'getAEVersion',
                from: 'website',
            }, function(res) {

               if (res.id) {



                    $('.ae-extension-check, .ae-modal-extension-check').hide();

                    $.each(config.exports, function () {
                        if (this.is_aliexpress ){
                            if (this.is_default) {
                                renderAEmodal(this.original.url);
                            }
                            renderAETable(this);
                        }


                    });

                    $('.ae-extension-content, .ae-modal-extension-content').show();
               }
               else {
                    $('.ae-extension-check, .ae-modal-extension-check').show();
                    $('.ae-extension-content, .ae-modal-extension-content').hide();
               }


            });

        }
    }, 1000);

function renderAETable(export_template) {

    window.AE_extensionSendMessage( { method: 'getAEProduct' ,
                            objectToSend: {single_product_url: export_template.original.url}}, function(res) {

        var ae_product_item_template = Handlebars.compile($("#ae-product-item").html());
        var context = { image: res.response.images[0],
                        title: res.title,
                        link: res.new_link,
                        product_id: res.product_id,
                        rating: res.rating,
                        review: res.review,
                        m_order: res.m_order,
                        store_link: res.store_link,
                        store: res.store,
                        store_feedbackx: res.store_feedbackx,
                        my_p_price: res.my_p_price,
                        eshipPriceValueToRender: res.eshipPriceValueToRender,
                        original_url: export_template.original.url,
                        company_id: res.company_id
                        };
        var html = ae_product_item_template(context);
        $('.ae-extension-content').append(html);

    });

}



function renderAEmodal(product_url) {

    window.AE_extensionSendMessage( { method: 'getAEProduct' ,
                            objectToSend: {single_product_url: product_url}}, function(res) {

                                        $('.ae-modal-item-cost').html("$"+res.my_p_price);
                                        $('.ae-modal-epacket-cost').html(res.eshipPriceValueToRender);
                                        $('.ae-modal-total-cost').html("$"+res.totalCost);
                                        $('.ae-modal-markup').html("$"+res.totalCost*2);

        $('#modal-ae-product .ae-open-in-ae').attr('data-product-url',product_url);
        $('.ae-get-pricing-data').attr('data-product-url',product_url);

        var ctx = document.getElementById('ae-chart');

        var myChart = new Chart(ctx, {
          type: 'horizontalBar',

          data: {
            labels: [''],
            datasets: [
              {
                label: 'Item Cost',
                data: [res.my_p_price],
                backgroundColor: '#EBCCD1',
              },
              {
                label: 'ePacket',
                data: [parseFloat(res.eshipPriceValueToRender.replace(/[^\d.-]/g, ''))],
                backgroundColor: '#FAEBCC',
              },
              {
                label: 'Markup',
                data: [res.totalCost*2],
                backgroundColor: '#D6E9C6',
              }
            ]
          },
          options: {
            maintainAspectRatio: false,
            scales: {
              xAxes: [{ stacked: true, display: false }],
              yAxes: [{ stacked: true }]
            },
            legend: {display: true}
          }
        });

    });

}

$(document).on('click', '.ae-open-in-ae', function() {
        var product_url = $(this).data('productUrl');
        window.AE_extensionSendMessage(  { "method": "openNewTab", "url": product_url  }, function(res) {
        });
    });
$(document).on('click', '.ae-open-topsells', function() {
        var store_link = $(this).data('storeLink');
        window.AE_extensionSendMessage(  { "method": "openTopSellsTab", "store_link": store_link }, function(res) {
            if (res.error) {
                alert(res.error);
            }

        });
    });
$(document).on('click', '.ae-open-trending', function() {
        var store_link = $(this).data('storeLink');
        var product_id = $(this).data('productId');
        var company_id = $(this).data('companyId');
        window.AE_extensionSendMessage(  { "method": "openTrendingProductsTab", "store_link": store_link, "product_id": product_id, "company_id": company_id }, function(res) {
            if (res.error) {
                alert(res.error);
            }

        });
    });



$('.ae-get-pricing-data').click(function (e) {
    e.preventDefault();
    $('#modal-ae-product').modal('show');
});


})();
