from django.conf.urls import patterns, include, url

from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    url(r'', include('leadgalaxy.urls')),
    url(r'^subscription/', include('stripe_subscription.urls')),
    url(r'^marketing/', include('product_feed.urls')),
    url(r'^pages/', include('article.urls')),
    url(r'^accounts/', include('django.contrib.auth.urls')),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^hijack/', include('hijack.urls')),
)


admin.site.site_header = 'Shopified App'
admin.site.login_template = 'registration/login.html'
