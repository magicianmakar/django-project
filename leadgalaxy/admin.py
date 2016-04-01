from django.contrib import admin
from .models import *
from django import forms

from django.core.urlresolvers import reverse


@admin.register(GroupPlan)
class GroupPlanAdmin(admin.ModelAdmin):
    list_display = ('title', 'montly_price', 'description', 'stores', 'products',
                    'boards', 'slug', 'register_hash', 'permissions_count')

    exclude = ('default_plan',)
    filter_horizontal = ('permissions',)
    prepopulated_fields = {'slug': ('title',)}


@admin.register(FeatureBundle)
class FeatureBundleAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'register_hash', 'permissions_count')
    filter_horizontal = ('permissions',)
    prepopulated_fields = {'slug': ('title',)}


@admin.register(UserUpload)
class UserUploadAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('product',)
    search_fields = ['url']

    def view_on_site(self, obj):
        return obj.url


@admin.register(ShopifyBoard)
class ShopifyBoardAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('products',)
    search_fields = ['title']


@admin.register(ShopifyProduct)
class ShopifyProductAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store_', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('parent_product', 'shopify_export', 'store', 'user')
    ordering = ('-updated_at',)
    search_fields = ['data', 'notes', 'price_notification_id']

    def store_(self, obj):
        return obj.store.title

    def view_on_site(self, obj):
        return reverse('product_view', kwargs={'pid': obj.id})


@admin.register(ShopifyProductExport)
class ShopifyProductExportAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'created_at')
    raw_id_fields = ('store',)
    search_fields = ['original_url', 'shopify_id']


@admin.register(ShopifyOrder)
class ShopifyOrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'line_id', 'shopify_status', 'store', 'source_id', 'get_source_status',
                    'status_updated_at', 'seen', 'hidden', 'check_count', 'source_tracking',
                    'created_at', 'updated_at')

    list_filter = ('shopify_status', 'source_status', 'seen', 'hidden',)
    search_fields = ['order_id', 'line_id', 'source_id', 'source_tracking', 'data']


@admin.register(ShopifyStore)
class ShopifyStoreAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'is_active', 'created_at', 'updated_at')
    search_fields = ['title', 'api_url', 'store_hash']


@admin.register(ShopifyWebhook)
class ShopifyWebhookAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'topic', 'call_count', 'created_at', 'updated_at')


@admin.register(AccessToken)
class AccessTokenAdmin(admin.ModelAdmin):
    list_display = ('token', 'user', 'created_at', 'updated_at')
    search_fields = ['token']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'country', 'timezone', 'status')
    list_filter = ('plan', 'status', 'bundles')
    search_fields = ['emails', 'country', 'timezone']

    def get_form(self, request, obj=None, **kwargs):
        self.instance = obj  # Capture instance before the form gets generated
        return super(UserProfileAdmin, self).get_form(request, obj=obj, **kwargs)

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        if db_field.name == 'bundles':
            kwargs['widget'] = forms.widgets.CheckboxSelectMultiple()
        elif db_field.name == 'subuser_stores' and self.instance:
            kwargs['widget'] = forms.widgets.CheckboxSelectMultiple()

            # restrict role queryset to those related to this instance:
            if self.instance.subuser_parent is not None:
                kwargs['queryset'] = self.instance.subuser_parent.shopifystore_set.all()
            else:
                kwargs['queryset'] = ShopifyStore.objects.none()

        return super(UserProfileAdmin, self).formfield_for_manytomany(
            db_field, request=request, **kwargs)


@admin.register(AppPermission)
class AppPermissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ['name', 'description']


@admin.register(PlanRegistration)
class PlanRegistrationAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'user', 'email', 'register_hash', 'sender', 'expired', 'created_at', 'updated_at')
    list_filter = ('expired',)
    search_fields = ['data', 'email', 'register_hash']


@admin.register(ShopifyProductImage)
class ShopifyProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'variant', 'store')
    search_fields = ['image']


@admin.register(AliexpressProductChange)
class AliexpressProductChangeAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'seen', 'hidden', 'created_at', 'updated_at')
    raw_id_fields = ('product', 'user')
    list_filter = ('seen', 'hidden',)
    search_fields = ['data']


@admin.register(PlanPayment)
class PlanPaymentAdmin(admin.ModelAdmin):
    list_display = ('provider', 'payment_id', 'transaction_type', 'fullname',
                    'email', 'user', 'created_at')
    list_filter = ('provider', 'transaction_type',)
    search_fields = ['fullname', 'email', 'payment_id', 'data']
