from django.conf.urls import url

import order_exports.views

urlpatterns = [
    url(r'^$', order_exports.views.index, name='order_exports_index'),
    url(r'^vendor-autocomplete$', order_exports.views.vendor_autocomplete, name='order_exports_vendor_autocomplete'),
    url(r'^add$', order_exports.views.add, name='order_exports_add'),
    url(r'^edit/(?P<order_export_id>[\d]+)$', order_exports.views.edit, name='order_exports_edit'),
    url(r'^delete/(?P<order_export_id>[\d]+)$', order_exports.views.delete, name='order_exports_delete'),
    url(r'^logs/(?P<order_export_id>[\d]+)$', order_exports.views.logs, name='order_exports_logs'),
    url(r'^generated/(?P<order_export_id>[\d]+)/(?P<code>[\w]+)$', order_exports.views.generated, name='order_exports_generated'),
    url(r'^delete/vendor/(?P<vendor_id>[\d]+)$', order_exports.views.delete_vendor, name='order_exports_delete_vendor'),
    url(r'^fulfill/(?P<order_export_id>[\d]+)/(?P<code>[\w]+)/(?P<order_id>[\d]+)/(?P<line_item_id>[\d]+)$',
        order_exports.views.fulfill_order, name='order_exports_fulfill_order')
]
