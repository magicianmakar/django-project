orders_list_response = {
    'alibaba_seller_order_list_response': {
        'result': {
            'success': True,
            'value': {
                "order_list": {
                    "trade_ecology_order": [
                        {
                            "trade_id": "9999999",
                            "create_date": {
                                "timestamp": 123456789,
                                "format_date": "MMM. d, yyyy, HH:mm:ss z."
                            },
                            "modify_date": {
                                "timestamp": 123456789,
                                "format_date": "MMM. d, yyyy, HH:mm:ss z."
                            }
                        }
                    ]
                },
            },
        }
    }
}

order_get_reaponse = {
    "alibaba_seller_order_get_response":{
        "value":{
            "buyer":{
                "country":"US",
                "full_name":"jack ma",
                "e_account_id":"fsfds3124"
            },
            "create_date":{
                "timestamp":123456789,
                "format_date":"MMM. d, yyyy, HH:mm:ss z."
            },
            "export_service_type":"onetouch_service",
            "inspection_service_amount":{
                "amount":"123.00",
                "currency":"USD"
            },
            "order_products":{
                "trade_ecology_order_product":[
                    {
                        "name":"test",
                        "product_image":"\/\/fsfffs.jpg",
                        "quantity":"12.0000",
                        "sku_attributes":{
                            "sku_attribute":[
                                {
                                    "key":"color",
                                    "value":"order"
                                }
                            ]
                        },
                        "sku_id":"33",
                        "unit":"piece",
                        "unit_price":{
                            "amount":"123.00",
                            "currency":"USD"
                        },
                        "product_id":"123423",
                        "sku_code":"T14234",
                        "model_number":"RS3434"
                    }
                ]
            },
            "product_total_amount":{
                "amount":"123.00",
                "currency":"USD"
            },
            "remark":"hello",
            "seller":{
                "full_name":"jack ma",
                "login_id":"xxx",
                "is_admin":True,
                "email":"12343@test.com",
                "e_account_id":"fsfs312"
            },
            "shipment_fee":{
                "amount":"123.00",
                "currency":"USD"
            },
            "shipment_method":"air",
            "shipping_address":{
                "address":"xx",
                "alternate_address":"xx",
                "city":"xx",
                "contact_person":"xx",
                "country":"US",
                "fax":{
                    "area":"xx",
                    "country":"US",
                    "number":"xx"
                },
                "mobile":{
                    "area":"xx",
                    "country":"US",
                    "number":"xx"
                },
                "port":"1233",
                "province":"xx",
                "telephone":{
                    "area":"xx",
                    "country":"US",
                    "number":"xx"
                },
                "zip":"3000015",
                "country_code":"US",
                "port_code":"xxx",
                "province_code":"xxx",
                "city_code":"xxx"
            },
            "total_amount":{
                "amount":"123",
                "currency":"USD"
            },
            "trade_status":"trade_success",
            "trade_id":"12345",
            "contract_version":"12345432",
            "status_action":{
                "actions":{
                    "actions":[
                        {
                            "value":"order",
                            "name":"test",
                            "render_name":"查看支付链接"
                        }
                    ]
                },
                "status":"trade_success"
            },
            "shipment_insurance_fee":{
                "currency":"USD",
                "amount":"123.00"
            },
            "trade_term":"FOB",
            "shipment_date":{
                "type":"relative",
                "duration":2,
                "date":{
                    "format_date":"MMM. d, yyyy, HH:mm:ss z.",
                    "timestamp":123456789
                }
            },
            "advance_amount":{
                "currency":"USD",
                "amount":"123.00"
            },
            "balance_amount":{
                "currency":"USD",
                "amount":"123.00"
            },
            "fulfillment_channel":"TAD",
            "list_remark":"xxx",
            "carrier":{
                "code":"FEDEX",
                "name":"test"
            },
            "pay_step":"ADVANCE",
            "adjust_amount":{
                "currency":"USD",
                "amount":"123.00"
            },
            "discount_amount":{
                "currency":"USD",
                "amount":"123.00"
            },
            "biz_code":"1020203和1020206，属于RFP类",
            "channel_refer_id":"12345",
            "draft_role":"seller 或 buyer",
            "item_status":"normal \/ delete",
            "source":"42432"
        }
    }
}

product_get_response = {
    'alibaba_dropshipping_product_get_response': {
        'value': {
            'distribution_sale_product': [{
                'description': '''<div data-host="112114235" data-magic-global="%7B%22bizId%22%3A3979543113%2C%22pageId%22%3A20006980151%2C%22siteId%22%3A5007273083%7D" data-id="detail_decorate_root" id="detail_decorate_root"><style>#detail_decorate_root .magic-0{width:750px}#detail_decorate_root .magic-1{overflow:hidden;width:750px;height:974.0506329113925px;margin-top:0;margin-bottom:0;margin-left:0;margin-right:0}#detail_decorate_root .magic-2{margin-top:0;margin-left:0;width:750.0000000000001px;height:974.0506329113925px}#detail_decorate_root .magic-3{overflow:hidden;width:750px;height:1000px;margin-top:0;margin-bottom:0;margin-left:0;margin-right:0}#detail_decorate_root .magic-4{margin-top:0;margin-left:0;width:750px;height:1000px}#detail_decorate_root .magic-5{border-bottom-style:solid;border-bottom-color:#53647a;font-family:Roboto;font-size:24px;color:#53647a;font-style:normal;border-bottom-width:2px;padding-top:8px;padding-bottom:4px}#detail_decorate_root .magic-6{width:750px;border-collapse:collapse}#detail_decorate_root .magic-7{min-height:18px;padding:5px 10px;width:259px;min-height:18px;box-sizing:content-box}#detail_decorate_root .magic-8{font-size:18px}#detail_decorate_root .magic-9{min-height:18px;padding:5px 10px;width:442px;min-height:18px;box-sizing:content-box}#detail_decorate_root .magic-10{overflow:hidden;width:750px;height:808.8607594936709px;margin-top:0;margin-bottom:0;margin-left:0;margin-right:0}#detail_decorate_root .magic-11{margin-top:0;margin-left:0;width:750.0000000000001px;height:808.8607594936709px}#detail_decorate_root .magic-12{overflow:hidden;width:750px;height:945.5696202531647px;margin-top:0;margin-bottom:0;margin-left:0;margin-right:0}#detail_decorate_root .magic-13{margin-top:0;margin-left:0;width:750.0000000000001px;height:945.5696202531647px}#detail_decorate_root .magic-14{overflow:hidden;width:750px;height:1240.8227848101267px;margin-top:0;margin-bottom:0;margin-left:0;margin-right:0}#detail_decorate_root .magic-15{margin-top:0;margin-left:0;width:750.0000000000001px;height:1240.8227848101267px}#detail_decorate_root .magic-16{overflow:hidden;width:750px;height:881.9620253164558px;margin-top:0;margin-bottom:0;margin-left:0;margin-right:0}#detail_decorate_root .magic-17{margin-top:0;margin-left:0;width:750.0000000000001px;height:881.9620253164558px}#detail_decorate_root .magic-18{overflow:hidden;width:750px;height:1076.5822784810127px;margin-top:0;margin-bottom:0;margin-left:0;margin-right:0}#detail_decorate_root .magic-19{margin-top:0;margin-left:0;width:750.0000000000001px;height:1076.5822784810127px}#detail_decorate_root .magic-20{overflow:hidden;width:750px;height:837.3417721518988px;margin-top:0;margin-bottom:0;margin-left:0;margin-right:0}#detail_decorate_root .magic-21{margin-top:0;margin-left:0;width:750.0000000000001px;height:837.3417721518988px}#detail_decorate_root .magic-22{overflow:hidden;width:750px;height:831.6455696202532px;margin-top:0;margin-bottom:0;margin-left:0;margin-right:0}#detail_decorate_root .magic-23{margin-top:0;margin-left:0;width:750.0000000000001px;height:831.6455696202532px}#detail_decorate_root .magic-24{overflow:hidden;width:750px;height:944.6202531645571px;margin-top:0;margin-bottom:0;margin-left:0;margin-right:0}#detail_decorate_root .magic-25{margin-top:0;margin-left:0;width:750.0000000000001px;height:944.6202531645571px}#detail_decorate_root .magic-26{vertical-align:top}#detail_decorate_root .magic-27{vertical-align:top;display:block;padding-right:4px;box-sizing:border-box;padding-left:4px}#detail_decorate_root .magic-28{vertical-align:top;padding-bottom:4px;box-sizing:border-box;padding-top:4px}#detail_decorate_root .magic-29{padding:0;margin:0;white-space:pre-wrap;font-size:14px}#detail_decorate_root .magic-30{margin-bottom:10px;overflow:hidden}#detail_decorate_root .magic-31{overflow:hidden;width:247.33333333333334px;height:247.33333333333337px;margin-top:0;margin-bottom:0;margin-left:0;margin-right:0}#detail_decorate_root .magic-32{margin-top:0;margin-left:0;width:247px;height:160px}#detail_decorate_root .magic-33{overflow:hidden;width:247.33333333333334px;height:247.33333333333337px;margin-top:0;margin-bottom:0;margin-left:4px;margin-right:0}#detail_decorate_root .magic-34{margin-top:0;margin-left:0;width:247px;height:185px}</style>\n      <div module-id="20159892162" module-title="detailSingleImage" render="true" class="J_module"><div class="icbu-pc-images magic-0"><div><div class="flex-layout-v"><div class="flex-layout-h magic-0"><div class="magic-1"><img src="//sc02.alicdn.com/kf/H7774433081ad45c7b4b93513f7b642f4f/234256372/H7774433081ad45c7b4b93513f7b642f4f.jpg" class="magic-2"></div></div></div></div></div></div>\n      \n      <div module-id="20159892163" module-title="detailSingleImage" render="true" class="J_module"><div class="icbu-pc-images magic-0"><div><div class="flex-layout-v"><div class="flex-layout-h magic-0"><div class="magic-3"><img src="//sc01.alicdn.com/kf/H2626984ce3e948f19d01c53d2c5d4288G/234256372/H2626984ce3e948f19d01c53d2c5d4288G.jpg" class="magic-4"></div></div></div></div></div></div>\n      \n      <div module-id="20159892164" module-title="detailProductNavigation" render="true" class="J_module"><div id="ali-anchor-AliMagic-qru6ag" data-section="AliMagic-qru6ag" data-section-title="Specification" class="magic-5">Specification</div></div>\n      \n      <div module-id="20159892165" module-title="detailTableHorizontal" render="true" class="J_module"><div class="ife-detail-decorate-table"><table class="has-title is-zebra hight-light-first-column all magic-6"><tbody><tr><td colspan="1" rowspan="1"><div class="magic-7"><b><font class="magic-8">Model Number</font></b></div></td><td colspan="1" rowspan="1"><div class="magic-9"><b><font class="magic-8">T500</font></b></div></td></tr><tr><td colspan="1" rowspan="1"><div class="magic-7"><b><font class="magic-8">Case</font></b></div></td><td colspan="1" rowspan="1"><div class="magic-9"><b><font class="magic-8">Zinc Alloy</font></b></div></td></tr><tr><td colspan="1" rowspan="1"><div class="magic-7"><b><font class="magic-8">Charging method</font></b></div></td><td colspan="1" rowspan="1"><div class="magic-9"><b><font class="magic-8">Magnetic charging</font></b></div></td></tr><tr><td colspan="1" rowspan="1"><div class="magic-7"><b><font class="magic-8">Screen Size</font></b></div></td><td colspan="1" rowspan="1"><div class="magic-9"><b><font class="magic-8">1.54-inch IPS Full Touch,240*240pixel</font></b></div></td></tr><tr><td colspan="1" rowspan="1"><div class="magic-7"><b><font class="magic-8">Bluetooth version</font></b></div></td><td colspan="1" rowspan="1"><div class="magic-9"><b><font class="magic-8">4.2 Bluetooth Call,Music Control</font></b></div></td></tr><tr><td colspan="1" rowspan="1"><div class="magic-7"><b><font class="magic-8">Waterproof</font></b></div></td><td colspan="1" rowspan="1"><div class="magic-9"><b><font class="magic-8">IP67 Waterproof</font></b></div></td></tr><tr><td colspan="1" rowspan="1"><div class="magic-7"><b><font class="magic-8">Battery</font></b></div></td><td colspan="1" rowspan="1"><div class="magic-9"><b><font class="magic-8">200mAh Lithium polymer battery&#xA0;</font></b></div></td></tr></tbody></table></div></div>\n      \n      <div module-id="20159892166" module-title="detailSingleImage" render="true" class="J_module"><div class="icbu-pc-images magic-0"><div><div class="flex-layout-v"><div class="flex-layout-h magic-0"><div class="magic-10"><img src="//sc02.alicdn.com/kf/H0562e752c5ca4309b0ba70b00040bbc9Y/234256372/H0562e752c5ca4309b0ba70b00040bbc9Y.jpg" class="magic-11"></div></div></div></div></div></div>\n      \n      <div module-id="20159892167" module-title="detailSingleImage" render="true" class="J_module"><div class="icbu-pc-images magic-0"><div><div class="flex-layout-v"><div class="flex-layout-h magic-0"><div class="magic-12"><img src="//sc02.alicdn.com/kf/H95b60ab168804fdea30add3af5bfcb84G/234256372/H95b60ab168804fdea30add3af5bfcb84G.jpg" class="magic-13"></div></div></div></div></div></div>\n      \n      <div module-id="20159892168" module-title="detailProductNavigation" render="true" class="J_module"><div id="ali-anchor-AliMagic-8890ul" data-section="AliMagic-8890ul" data-section-title="Product Description" class="magic-5">Product Description</div></div>\n      \n      <div module-id="20159892171" module-title="detailSingleImage" render="true" class="J_module"><div class="icbu-pc-images magic-0"><div><div class="flex-layout-v"><div class="flex-layout-h magic-0"><div class="magic-14"><img src="//sc02.alicdn.com/kf/H2cf759f968c04036b0b870e0e4a841894/234256372/H2cf759f968c04036b0b870e0e4a841894.jpg" class="magic-15"></div></div></div></div></div></div>\n      \n      <div module-id="20159892172" module-title="detailSingleImage" render="true" class="J_module"><div class="icbu-pc-images magic-0"><div><div class="flex-layout-v"><div class="flex-layout-h magic-0"><div class="magic-16"><img src="//sc01.alicdn.com/kf/Hce333fb7d13f43eb9d7952fda9d7e0c6V/234256372/Hce333fb7d13f43eb9d7952fda9d7e0c6V.jpg" class="magic-17"></div></div></div></div></div></div>\n      \n      <div module-id="20159892173" module-title="detailSingleImage" render="true" class="J_module"><div class="icbu-pc-images magic-0"><div><div class="flex-layout-v"><div class="flex-layout-h magic-0"><div class="magic-18"><img src="//sc01.alicdn.com/kf/H8b3e5bb1bebe48778d7c05e5549080fef/234256372/H8b3e5bb1bebe48778d7c05e5549080fef.jpg" class="magic-19"></div></div></div></div></div></div>\n      \n      <div module-id="20159892174" module-title="detailSingleImage" render="true" class="J_module"><div class="icbu-pc-images magic-0"><div><div class="flex-layout-v"><div class="flex-layout-h magic-0"><div class="magic-20"><img src="//sc01.alicdn.com/kf/H2cbe1f0c992c4829b0c45f3d844fa4feN/234256372/H2cbe1f0c992c4829b0c45f3d844fa4feN.jpg" class="magic-21"></div></div></div></div></div></div>\n      \n      <div module-id="20159892175" module-title="detailSingleImage" render="true" class="J_module"><div class="icbu-pc-images magic-0"><div><div class="flex-layout-v"><div class="flex-layout-h magic-0"><div class="magic-22"><img src="//sc01.alicdn.com/kf/H94c5dc468b5e45a9878b69340eb1455cQ/234256372/H94c5dc468b5e45a9878b69340eb1455cQ.jpg" class="magic-23"></div></div></div></div></div></div>\n      \n      <div module-id="20159892176" module-title="detailSingleImage" render="true" class="J_module"><div class="icbu-pc-images magic-0"><div><div class="flex-layout-v"><div class="flex-layout-h magic-0"><div class="magic-24"><img src="//sc02.alicdn.com/kf/H2bdc524e555e42eca8a952dbc1bc3af5D/234256372/H2bdc524e555e42eca8a952dbc1bc3af5D.jpg" class="magic-25"></div></div></div></div></div></div>\n      \n      <div module-id="20159892177" module-title="detailProductNavigation" render="true" class="J_module"><div id="ali-anchor-AliMagic-50vupb" data-section="AliMagic-50vupb" data-section-title="Packing &amp; Delivery" class="magic-5">Packing &amp; Delivery</div></div>\n      \n      <div module-id="20159892178" module-title="detailSingleImage" render="true" class="J_module"><div class="icbu-pc-images magic-0"><div><div class="flex-layout-v"><div class="flex-layout-h magic-0"><div class="magic-3"><img src="//sc01.alicdn.com/kf/H0b6c29920d854853a852b69e9b12b54dS/234256372/H0b6c29920d854853a852b69e9b12b54dS.jpg" class="magic-4"></div></div></div></div></div></div>\n      \n      <div module-id="20159892179" module-title="detailSingleImage" render="true" class="J_module"><div class="icbu-pc-images magic-0"><div><div class="flex-layout-v"><div class="flex-layout-h magic-0"><div class="magic-3"><img src="//sc01.alicdn.com/kf/H663c578e570a480a967b1f9771bb539dg/234256372/H663c578e570a480a967b1f9771bb539dg.jpg" class="magic-4"></div></div></div></div></div></div>\n      \n      <div module-id="20159892180" module-title="detailTextContent" render="true" class="J_module"><div class="detail-decorate-json-renderer-container"><div class="magic-26"><div class="magic-27"><div class="magic-28"><div class="magic-29">1 piece product pack into 1 color box ,100pcs color box pack into 1 cartoon box</div></div></div></div></div></div>\n      \n      <div module-id="20159892181" module-title="detailSellerRecommend" render="true" class="J_module"><div data-magic="{&quot;mds&quot;:{&quot;assetsVersion&quot;:&quot;0.0.14&quot;,&quot;assetsPackageName&quot;:&quot;icbumod&quot;,&quot;moduleNameAlias&quot;:&quot;icbu-pc-detailSellerRecommend&quot;,&quot;moduleData&quot;:{&quot;config&quot;:{&quot;miniSiteUrl&quot;:&quot;https://alisite-mobile.alibaba.com/minisite/243480296/productlist.html&quot;,&quot;columnCount&quot;:3,&quot;titleKey&quot;:6,&quot;url&quot;:&quot;https://tanzou.en.alibaba.com/productlist.html&quot;,&quot;products&quot;:[1600110250300,1600110165660,1600123686201,1600121849687,1600121341467,1600121294752]}}},&quot;version&quot;:1}" class="icbu-pc-detailSellerRecommend magic-30"></div></div>\n      \n      <div module-id="20159892182" module-title="detailProductNavigation" render="true" class="J_module"><div id="ali-anchor-AliMagic-3ureag" data-section="AliMagic-3ureag" data-section-title="Company Profile" class="magic-5">Company Profile</div></div>\n      \n      <div module-id="20159892183" module-title="detailMultiImages" render="true" class="J_module"><div class="icbu-pc-images magic-0"><div><div class="flex-layout-v"><div class="flex-layout-h magic-0"><div class="magic-31"><img src="https://sc01.alicdn.com/kf/HTB1XPb.x9tYBeNjSspaq6yOOFXaR.jpg" data-id="child-image-0" class="magic-32"></div><div class="magic-33"><img src="https://sc01.alicdn.com/kf/HTB1SoX9x1uSBuNjSsplq6ze8pXab.jpg" data-id="child-image-1" class="magic-34"></div><div class="magic-33"><img src="https://sc01.alicdn.com/kf/HTB1cSQxx_tYBeNjy1Xdq6xXyVXaT.jpg" data-id="child-image-2" class="magic-34"></div></div></div></div></div></div>\n      \n      <div module-id="20159892184" module-title="detailTextContent" render="true" class="J_module"><div class="detail-decorate-json-renderer-container"><div class="magic-26"><div class="magic-27"><div class="magic-28"><div class="magic-29">Dongguan Tanzou Tech Co., Ltd. is a company that can provide design, and complete solution for wearable device products, such like smart watches, smart bracelet, smart wrist bands, and VR glass,tws earphones etc.</div></div></div></div></div></div>\n      \n      <div module-id="20159892185" module-title="detailProductNavigation" render="true" class="J_module"><div id="ali-anchor-AliMagic-nksj3p" data-section="AliMagic-nksj3p" data-section-title="FAQ" class="magic-5">FAQ</div></div>\n      \n      <div module-id="20159892186" module-title="detailTextContent" render="true" class="J_module"><div class="detail-decorate-json-renderer-container"><div class="magic-26"><div class="magic-27"><div class="magic-28"><div class="magic-29"><b>1. who are we?</b><br>We are based in Guangdong, China, start from 2017,sell to North America(15.00%),Mid East(15.00%),South Asia(10.00%),Western Europe(10.00%),Domestic Market(5.00%),Southeast Asia(5.00%),Southern Europe(5.00%),Northern Europe(5.00%),Central America(5.00%),South America(5.00%),Eastern Europe(5.00%),Eastern Asia(5.00%),Oceania(5.00%),Africa(5.00%). There are total about 51-100 people in our office.<br><br><b>2. how can we guarantee quality?</b><br>Always a pre-production sample before mass production;<br>Always final Inspection before shipment;<br><br><b>3.what can you buy from us?</b><br>Smart Watch,Smartwatch,Smart Wristband,Smart Band,Smart Bracelet<br><br><b>4. why should you buy from us not from other suppliers?</b><br>We specialize in providing customers with advanced fashion technology consumer electronics products allow people to enjoy the happiness brought by technological progress.<br><br><b>5. what services can we provide?</b><br>Accepted Delivery Terms: FOB,CFR,CIF,EXW,DDP,DDU,Express Delivery&#xFF1B;<br>Accepted Payment Currency:USD,EUR,GBP,CNY;<br>Accepted Payment Type: T/T,L/C,PayPal,Western Union;<br>Language Spoken:English,Chinese</div></div></div></div></div></div>\n      </div>''',
     'detail_url': 'https://www.alibaba.com/product-detail/1600124642247.html',
     'is_can_place_order': True,
     'e_company_id': '634215',
     'keywords': {'string': ['t500 smart watch', 'smartwatch t500', 't500']},
     'ladder_period_list': {'ladder_period': [{'max_quantity': 100,
        'min_quantity': 1,
        'process_period': 5},
       {'max_quantity': 500, 'min_quantity': 101, 'process_period': 7},
       {'max_quantity': 1000, 'min_quantity': 501, 'process_period': 10}]},
     'main_image_url': 'https://sc04.alicdn.com/kf/Hbaa543ef00774305882c18bbf8078596R.jpg',
     'moq_and_price': {'min_order_quantity': '3',
      'moq_delivery_period': 5,
      'moq_unit_price': {'amount': '6.9', 'currency': 'USD'},
      'unit': 'Unit(s)'},
     'name': 'T500 Serie 5 6 Watch Smartwatch BT Call 1.54-IN IPS Full Screen Multi Sport Mode Android Phone Smart Watch IWO',
     'price_range': '3.90~6.90',
     'product_id': 1600124642247,
     'product_sku_list': {'product_sku': [{'image_url': 'https://sc04.alicdn.com/kf/H43864d0dda5c4838b804d5146b4e0482Y.jpg',
        'ladder_price_list': {'ladder_price': [{'max_quantity': 99,
           'min_quantity': 3,
           'price': {'amount': '6.9', 'currency': 'USD'}},
          {'max_quantity': 999,
           'min_quantity': 100,
           'price': {'amount': '6.7', 'currency': 'USD'}},
          {'max_quantity': 9999,
           'min_quantity': 1000,
           'price': {'amount': '6.5', 'currency': 'USD'}},
          {'max_quantity': -1,
           'min_quantity': 10000,
           'price': {'amount': '3.9', 'currency': 'USD'}}]},
        'sku_id': 100468914436,
        'sku_name_value_list': {'product_sku_name_value': [{'attr_name_desc': 'Color',
           'attr_name_id': 191288010,
           'attr_value_desc': 'Pink',
           'attr_value_id': 3328925,
           'attr_value_image': 'https://sc04.alicdn.com/kf/H43864d0dda5c4838b804d5146b4e0482Y.jpg_100x100.jpg'}]}},
       {'image_url': 'https://sc04.alicdn.com/kf/H52cf5c967e994a65b5c31b62743c6087e.jpg',
        'ladder_price_list': {'ladder_price': [{'max_quantity': 99,
           'min_quantity': 3,
           'price': {'amount': '6.9', 'currency': 'USD'}},
          {'max_quantity': 999,
           'min_quantity': 100,
           'price': {'amount': '6.7', 'currency': 'USD'}},
          {'max_quantity': 9999,
           'min_quantity': 1000,
           'price': {'amount': '6.5', 'currency': 'USD'}},
          {'max_quantity': -1,
           'min_quantity': 10000,
           'price': {'amount': '3.9', 'currency': 'USD'}}]},
        'sku_id': 100468914434,
        'sku_name_value_list': {'product_sku_name_value': [{'attr_name_desc': 'Color',
           'attr_name_id': 191288010,
           'attr_value_desc': 'White',
           'attr_value_id': 3331185,
           'attr_value_image': 'https://sc04.alicdn.com/kf/H52cf5c967e994a65b5c31b62743c6087e.jpg_100x100.jpg'}]}},
       {'image_url': 'https://sc04.alicdn.com/kf/Ha3221c23f6564c8492ec80e3a4fadba9Y.jpg',
        'ladder_price_list': {'ladder_price': [{'max_quantity': 99,
           'min_quantity': 3,
           'price': {'amount': '6.9', 'currency': 'USD'}},
          {'max_quantity': 999,
           'min_quantity': 100,
           'price': {'amount': '6.7', 'currency': 'USD'}},
          {'max_quantity': 9999,
           'min_quantity': 1000,
           'price': {'amount': '6.5', 'currency': 'USD'}},
          {'max_quantity': -1,
           'min_quantity': 10000,
           'price': {'amount': '3.9', 'currency': 'USD'}}]},
        'sku_id': 100468914435,
        'sku_name_value_list': {'product_sku_name_value': [{'attr_name_desc': 'Color',
           'attr_name_id': 191288010,
           'attr_value_desc': 'Black',
           'attr_value_id': 3327837,
           'attr_value_image': 'https://sc04.alicdn.com/kf/Ha3221c23f6564c8492ec80e3a4fadba9Y.jpg_100x100.jpg'}]}}]}}]},
  'request_id': '355i5k5sxfa4'}}

create_order_response = {
    "alibaba_buynow_order_create_response":{
        "value":{
            "pay_url":"https:\/\/biz.alibaba.com\/ta\/detail.htm?orderId=1234",
            "trade_id":"100006192"
        }
    }
}

get_shipping_cost_response = {
    "alibaba_shipping_freight_calculate_response":{
        "values":{
            "value":[{
                "shipping_type":"EXPRESS",
                "trade_term":"DAP",
                "destination_country":"US",
                "vendor_code":"Alibaba.com Economy Express (3C)",
                "vendor_name":"Alibaba.com Economy Express (3C)",
                "fee":{
                    "currency":"USD",
                    "amount":"20"
                },
                "shipping_time":"12~20",
                "dispatch_country":"CN"
            }]
        }
    }
}

get_order_payments_response = {
    "alibaba_seller_order_fund_get_response":{
        "value":{
            "fund_pay_list":{
                "fund_pay":[
                    {
                        "pay_amount":{
                            "amount":"12.00",
                            "currency":"USD"
                        },
                        "pay_method":"TT",
                        "pay_status":"UNPAY",
                        "pay_step":"ADVANCE",
                        "pay_time":{
                            "format_date":"MMM. d, yyyy, HH:mm:ss z.",
                            "timestamp":12345
                        },
                        "receive_amount":{
                            "amount":"12.00",
                            "currency":"USD"
                        },
                        "receive_time":{
                            "timestamp":12345,
                            "format_date":"MMM. d, yyyy, HH:mm:ss z."
                        },
                        "should_pay_amount":{
                            "amount":"12.00",
                            "currency":"USD"
                        }
                    }
                ]
            },
            "service_fee":{
                "amount":"1.00",
                "currency":"USD"
            },
            "refund_list":{
                "refund":[
                    {
                        "amount":{
                            "currency":"USD",
                            "amount":"2.00"
                        },
                        "refund_time":{
                            "timestamp":12345,
                            "format_date":"MMM. d, yyyy, HH:mm:ss z."
                        },
                        "id":123432
                    }
                ]
            }
        }
    }
}

consume_messages_response = {
    "tmc_messages_consume_response":{
        "messages":{
            "tmc_message":[
                {
                    "id":1234567,
                    "topic":"icbu_trade_ProductNotify",
                    "pub_app_key":"45671234",
                    "pub_time":"2000-01-01 00:00:00",
                    "user_nick":"helloworld",
                    "content":"{\"product_id\":1600199868314,\"seller_nick\":\"helloworld\"}",
                    "user_id":133728931470
                },
                {
                    "id":12345678,
                    "topic":"icbu_trade_ProductNotify",
                    "pub_app_key":"45671234",
                    "pub_time":"2000-01-01 00:00:00",
                    "user_nick":"helloworld",
                    "content":"{\"product_id\":1600191825486,\"seller_nick\":\"helloworld\"}",
                    "user_id":133728931470
                },
                {
                    "id":123456789,
                    "topic":"icbu_trade_ProductNotify",
                    "pub_app_key":"45671234",
                    "pub_time":"2000-01-01 00:00:00",
                    "user_nick":"helloworld",
                    "content":"{\"product_id\":1600191825486,\"seller_nick\":\"hello\"}",
                    "user_id":12346
                }
            ]
        }
    }
}
